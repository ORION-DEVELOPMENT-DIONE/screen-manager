"""Connectivity status service

Tracks two independent status signals and exposes them via AppState:

  state.wifi_connected   (bool) — Orange Pi has an active WiFi connection
  state.meter_paired     (bool) — ESP32 meter is reachable on the same network

WiFi detection
--------------
Calls nmcli every WIFI_CHECK_INTERVAL seconds (cheap, already used elsewhere).
Non-blocking: result is cached; stale cache is used on timeout.

Meter paired detection
----------------------
Uses the existing MQTT flow — MQTTManager already receives energy/metrics.
We just track the timestamp of the last received message.
If a message arrived within METER_TIMEOUT seconds → paired.
No new network calls, no ping, no ARP — piggybacks on the existing connection.

The service runs a single background thread that updates state every
STATUS_POLL_INTERVAL seconds. The main menu reads state directly — no
callbacks needed.
"""

import time
import threading
import logging
import subprocess

log = logging.getLogger(__name__)

WIFI_CHECK_INTERVAL = 10    # seconds between nmcli calls
METER_TIMEOUT       = 30    # seconds without MQTT message → meter offline
STATUS_POLL_INTERVAL = 5    # how often the thread refreshes


class ConnectivityService:
    def __init__(self, state):
        self.state = state
        self._thread = None
        self._stop   = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start background polling thread."""
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="connectivity"
        )
        self._thread.start()
        log.info("ConnectivityService started")

    def stop(self):
        self._stop.set()

    def notify_mqtt_message(self):
        """Call this from MQTTManager._handle_energy_data() on every message.
        Updates the meter-last-seen timestamp used for paired detection.
        """
        self.state.meter_last_seen = time.monotonic()

    # ── Background loop ───────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._check_wifi()
                self._check_meter()
            except Exception:
                log.exception("ConnectivityService poll error")
            self._stop.wait(STATUS_POLL_INTERVAL)

    def _check_wifi(self):
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                capture_output=True, text=True, timeout=3
            )
            connected = any(
                line.startswith("yes:") and line[4:].strip()
                for line in result.stdout.splitlines()
            )
            if self.state.wifi_connected != connected:
                log.info("WiFi status → %s", "connected" if connected else "disconnected")
            self.state.wifi_connected = connected
        except subprocess.TimeoutExpired:
            pass   # keep last known state
        except Exception as e:
            log.warning("WiFi check error: %s", e)

    def _check_meter(self):
        last_seen = getattr(self.state, "meter_last_seen", 0)
        paired = (time.monotonic() - last_seen) < METER_TIMEOUT
        if self.state.meter_paired != paired:
            log.info("Meter status → %s", "paired" if paired else "offline")
        self.state.meter_paired = paired