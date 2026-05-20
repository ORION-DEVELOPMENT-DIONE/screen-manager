"""
Phase Filter — Gateway-side sanitization of energy meter data.

Determines which phases are genuinely connected and strips noise
from disconnected phases before data reaches InfluxDB or the display.

Three detection layers:
  1. Trust ESP32 `connectedPhases` field if present (firmware v2+)
  2. Heuristic detection via sliding window analysis (firmware v1 fallback)  
  3. Hard noise floor clamp — absolute last defense

This module is the SINGLE source of truth for phase connectivity
on the gateway. All downstream consumers (InfluxDB, Grafana, display)
must use the filtered output.
"""

import logging
import time
from collections import deque
from typing import Optional

logger = logging.getLogger("PhaseFilter")

# ── Thresholds ──────────────────────────────────────────────────
# Noise on floating CT pins typically produces erratic spikes:
#   - Current: random 0-5A spikes with high variance
#   - Power: random 0-1000W spikes with high variance
# Real load produces steady readings with low variance.

CURRENT_NOISE_FLOOR = 0.15          # Amps — below this = noise
POWER_NOISE_FLOOR = 5.0             # Watts — below this = noise
SPIKE_CURRENT_MAX = 80.0            # Amps — above this = impossible spike
SPIKE_POWER_MAX = 20000.0           # Watts — above this = impossible spike

# Sliding window for heuristic detection
WINDOW_SIZE = 10                    # Last N readings per phase
VARIANCE_THRESHOLD_CURRENT = 2.0    # Connected phases have low variance
CONSISTENCY_RATIO = 0.7             # 70% of readings must be non-zero

# Phase state debouncing — prevent flapping
PHASE_STATE_HOLD_SEC = 60           # Hold state for 60s before allowing change
MIN_READINGS_FOR_DECISION = 5       # Need N readings before first decision


class PhaseDetector:
    """Per-device phase connectivity tracker."""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self._phase_labels = ["R", "Y", "B"]

        # Sliding windows: deque of (current, power) tuples per phase
        self._windows = [deque(maxlen=WINDOW_SIZE) for _ in range(3)]

        # Current phase state: None = undecided, True = connected, False = disconnected
        self._phase_state: list[Optional[bool]] = [None, None, None]

        # Timestamps of last state change per phase (for debouncing)
        self._last_state_change: list[float] = [0.0, 0.0, 0.0]

        # Total readings ingested
        self._reading_count = 0

        logger.debug(f"[{device_id}] PhaseDetector initialized")

    @property
    def phase_count(self) -> int:
        """Number of confirmed connected phases."""
        return sum(1 for s in self._phase_state if s is True)

    @property
    def connected_phases(self) -> list[bool]:
        """Which phases are connected. None treated as False."""
        return [s is True for s in self._phase_state]

    def filter_data(self, data: dict) -> dict:
        """
        Main entry point. Takes raw MQTT payload, returns sanitized copy.
        
        - If ESP32 sends `connectedPhases`, trusts it (Layer 1)
        - Otherwise runs heuristic detection (Layer 2)
        - Always applies hard noise clamp (Layer 3)
        - Recalculates totalPower from connected phases only
        - Adds `phaseCount` and `connectedPhases` to output
        """
        self._reading_count += 1
        phases = data.get("phases", [])

        if len(phases) != 3:
            logger.warning(f"[{self.device_id}] Expected 3 phases, got {len(phases)}")
            # Pad or truncate to 3
            while len(phases) < 3:
                phases.append({"current": 0, "power": 0})
            phases = phases[:3]

        # ── Layer 1: Trust ESP32 if connectedPhases present ──
        esp_connected = data.get("connectedPhases")
        if esp_connected and isinstance(esp_connected, list) and len(esp_connected) == 3:
            self._apply_esp_state(esp_connected)
        else:
            # ── Layer 2: Heuristic detection from data ──
            self._heuristic_update(phases)

        # ── Layer 3: Hard noise clamp + state enforcement ──
        filtered_phases = []
        recalc_total = 0.0

        for i, phase in enumerate(phases):
            current = phase.get("current", 0)
            power = phase.get("power", 0)

            if self._phase_state[i] is not True:
                # Phase disconnected — zero everything
                filtered_phases.append({"current": 0, "power": 0})
                continue

            # Connected phase — still apply spike rejection
            if current < CURRENT_NOISE_FLOOR:
                current = 0
            if power < POWER_NOISE_FLOOR:
                power = 0
            if current > SPIKE_CURRENT_MAX or power > SPIKE_POWER_MAX:
                logger.warning(
                    f"[{self.device_id}] Phase {self._phase_labels[i]} "
                    f"spike rejected: {current:.2f}A / {power:.1f}W"
                )
                current = 0
                power = 0

            filtered_phases.append({"current": current, "power": power})
            recalc_total += power

        # ── Build sanitized output ──
        out = dict(data)  # shallow copy
        out["phases"] = filtered_phases
        out["totalPower"] = round(recalc_total, 2)
        out["phaseCount"] = self.phase_count
        out["connectedPhases"] = self.connected_phases

        return out

    def _apply_esp_state(self, esp_connected: list[bool]):
        """Trust ESP32 detection, apply with debounce."""
        now = time.monotonic()
        for i in range(3):
            new_state = bool(esp_connected[i])
            old_state = self._phase_state[i]

            if old_state == new_state:
                continue

            # Allow initial state set immediately
            if old_state is None:
                self._phase_state[i] = new_state
                self._last_state_change[i] = now
                logger.info(
                    f"[{self.device_id}] Phase {self._phase_labels[i]} "
                    f"initial: {'CONNECTED' if new_state else 'DISCONNECTED'} (ESP32)"
                )
                continue

            # Debounce subsequent changes
            elapsed = now - self._last_state_change[i]
            if elapsed >= PHASE_STATE_HOLD_SEC:
                self._phase_state[i] = new_state
                self._last_state_change[i] = now
                logger.info(
                    f"[{self.device_id}] Phase {self._phase_labels[i]} "
                    f"changed: {'CONNECTED' if new_state else 'DISCONNECTED'} (ESP32, after {elapsed:.0f}s)"
                )

    def _heuristic_update(self, phases: list[dict]):
        """Fallback: detect phases from data patterns."""
        now = time.monotonic()

        for i, phase in enumerate(phases):
            current = phase.get("current", 0)
            power = phase.get("power", 0)
            self._windows[i].append((current, power))

        # Need enough data before deciding
        if self._reading_count < MIN_READINGS_FOR_DECISION:
            return

        for i in range(3):
            window = self._windows[i]
            if len(window) < MIN_READINGS_FOR_DECISION:
                continue

            currents = [r[0] for r in window]
            powers = [r[1] for r in window]

            # Check 1: How many readings are above noise floor?
            non_zero_count = sum(
                1 for c, p in window
                if c > CURRENT_NOISE_FLOOR or p > POWER_NOISE_FLOOR
            )
            consistency = non_zero_count / len(window)

            # Check 2: Variance of current readings
            if len(currents) > 1:
                mean_c = sum(currents) / len(currents)
                variance_c = sum((c - mean_c) ** 2 for c in currents) / len(currents)
            else:
                variance_c = 0

            # Check 3: Mean current level
            mean_current = sum(currents) / len(currents) if currents else 0

            # Decision logic:
            # Connected: consistent readings (>70% non-zero), low variance, meaningful current
            # Disconnected: sporadic readings OR high variance OR near-zero mean
            new_state = (
                consistency >= CONSISTENCY_RATIO
                and variance_c < VARIANCE_THRESHOLD_CURRENT
                and mean_current > CURRENT_NOISE_FLOOR
            )

            old_state = self._phase_state[i]

            if old_state == new_state:
                continue

            if old_state is None:
                self._phase_state[i] = new_state
                self._last_state_change[i] = now
                logger.info(
                    f"[{self.device_id}] Phase {self._phase_labels[i]} "
                    f"detected: {'CONNECTED' if new_state else 'DISCONNECTED'} "
                    f"(heuristic: consistency={consistency:.2f}, var={variance_c:.3f}, mean={mean_current:.3f})"
                )
                continue

            elapsed = now - self._last_state_change[i]
            if elapsed >= PHASE_STATE_HOLD_SEC:
                self._phase_state[i] = new_state
                self._last_state_change[i] = now
                logger.info(
                    f"[{self.device_id}] Phase {self._phase_labels[i]} "
                    f"changed: {'CONNECTED' if new_state else 'DISCONNECTED'} "
                    f"(heuristic, after {elapsed:.0f}s)"
                )

    def get_status(self) -> dict:
        """Diagnostic info for logging/debugging."""
        return {
            "device_id": self.device_id,
            "phase_count": self.phase_count,
            "phases": {
                self._phase_labels[i]: {
                    "connected": self._phase_state[i],
                    "window_size": len(self._windows[i]),
                }
                for i in range(3)
            },
            "total_readings": self._reading_count,
        }


class PhaseFilterManager:
    """
    Manages per-device PhaseDetectors.
    
    Usage in mqtt.py:
        from phase_filter import PhaseFilterManager
        
        phase_filter = PhaseFilterManager()
        
        def _handle_energy_data(self, data):
            # Filter BEFORE any processing
            data = phase_filter.filter(data)
            
            # Now proceed with clean data...
            self.state.energy_data = data
            self.data_logger.log_data(data)
            self.influx.write_energy_data(data)
    """

    def __init__(self):
        self._detectors: dict[str, PhaseDetector] = {}
        logger.info("PhaseFilterManager initialized")

    def filter(self, data: dict) -> dict:
        """Filter energy data. Auto-creates detector per device."""
        device_id = data.get("deviceId", "unknown")

        if device_id not in self._detectors:
            self._detectors[device_id] = PhaseDetector(device_id)

        return self._detectors[device_id].filter_data(data)

    def get_detector(self, device_id: str) -> Optional[PhaseDetector]:
        """Get detector for a specific device."""
        return self._detectors.get(device_id)

    def get_all_status(self) -> dict:
        """Diagnostic dump of all devices."""
        return {
            did: det.get_status()
            for did, det in self._detectors.items()
        }