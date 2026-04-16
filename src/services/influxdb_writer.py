"""
InfluxDB writer service for Orion Gateway.

Plugs into the existing data flow:
  ESP32 → MQTT (energy/metrics) → MQTTManager._handle_energy_data() → here

Usage in mqtt.py:
    from services.influxdb_writer import InfluxDBWriter
    self.influx = InfluxDBWriter()

    # In _handle_energy_data():
    self.influx.write_energy_data(data)

This runs ALONGSIDE the existing DataLogger (flat file) and EnergyAnalyzer
(in-memory deques). It does NOT replace them — it adds a durable, queryable
time-series layer that Grafana reads from.

Install: pip3 install influxdb-client
"""

import logging
import os
from datetime import datetime

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    INFLUXDB_AVAILABLE = True
except ImportError:
    INFLUXDB_AVAILABLE = False
    logging.warning("influxdb-client not installed — InfluxDB writes disabled. "
                    "Install with: pip3 install influxdb-client")


# ── Configuration (matches Ansible role defaults) ─────────────────────────
INFLUXDB_URL    = os.environ.get("INFLUXDB_URL",    "http://localhost:8086")
INFLUXDB_ORG    = os.environ.get("INFLUXDB_ORG",    "orion")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "energy_metrics")
INFLUXDB_TOKEN_FILE = os.environ.get("INFLUXDB_TOKEN_FILE",
                                      "/home/orangepi/.influxdb_token")


def _load_token():
    """Load InfluxDB token from file (written by Ansible role)."""
    try:
        with open(INFLUXDB_TOKEN_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        logging.warning(f"InfluxDB token file not found: {INFLUXDB_TOKEN_FILE}")
        return os.environ.get("INFLUXDB_TOKEN", "")
    except Exception as e:
        logging.error(f"Error reading InfluxDB token: {e}")
        return ""


class InfluxDBWriter:
    """Writes Orion energy metrics to local InfluxDB."""

    def __init__(self):
        self._client    = None
        self._write_api = None
        self._available = False
        self._error_count = 0
        self._max_errors  = 10   # Stop retrying after 10 consecutive failures

        if not INFLUXDB_AVAILABLE:
            logging.warning("InfluxDB client library not available — writes disabled")
            return

        token = _load_token()
        if not token:
            logging.warning("No InfluxDB token — writes disabled")
            return

        try:
            self._client = InfluxDBClient(
                url=INFLUXDB_URL,
                token=token,
                org=INFLUXDB_ORG,
                timeout=5000,           # 5 second timeout
                enable_gzip=True,       # Compress writes (saves bandwidth)
            )
            # Test connection
            health = self._client.health()
            if health.status == "pass":
                self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
                self._available = True
                logging.info(f"InfluxDB connected: {INFLUXDB_URL} "
                             f"(org={INFLUXDB_ORG}, bucket={INFLUXDB_BUCKET})")
            else:
                logging.warning(f"InfluxDB unhealthy: {health.message}")
        except Exception as e:
            logging.warning(f"InfluxDB connection failed: {e} — writes disabled")

    @property
    def available(self):
        return self._available

    def write_energy_data(self, data: dict):
        """
        Write an energy metrics payload to InfluxDB.

        Expects the same JSON dict that arrives from the ESP32:
        {
            "deviceId": "F8B3B77FEAF4",
            "timestamp": "2026-02-11 19:35:53",
            "battery": 82.36,
            "voltage": 217.72,
            "totalPower": 2150.05,
            "energyTotal": 0.00092,
            "phases": [
                {"current": 3.14, "power": 721.50},
                {"current": 3.06, "power": 703.61},
                {"current": 3.15, "power": 724.93}
            ]
        }
        """
        if not self._available:
            return

        if self._error_count >= self._max_errors:
            return

        try:
            device_id = data.get("deviceId", "unknown")

            # Use current UTC time (ESP32 timestamp has timezone offset issues)
            dt = datetime.utcnow()

            # Build the point
            point = (
                Point("energy")
                .tag("deviceId", device_id)
                .field("voltage",    float(data.get("voltage", 0)))
                .field("totalPower", float(data.get("totalPower", 0)))
                .field("energyTotal", float(data.get("energyTotal", 0)))
                .field("battery",    float(data.get("battery", 0)))
                .time(dt, WritePrecision.S)
            )

            # Per-phase fields (flattened for easier Grafana queries)
            phases = data.get("phases", [])
            phase_labels = ["r", "y", "b"]
            for i, phase in enumerate(phases):
                if i < len(phase_labels):
                    label = phase_labels[i]
                    point.field(f"current_{label}", float(phase.get("current", 0)))
                    point.field(f"power_{label}",   float(phase.get("power", 0)))

            # Optional fields (present in some payloads)
            if "runTime" in data:
                point.field("runTime", int(data["runTime"]))
            if "totalSleepTime" in data:
                point.field("totalSleepTime", int(data["totalSleepTime"]))

            self._write_api.write(bucket=INFLUXDB_BUCKET, record=point)
            self._error_count = 0  # Reset on success

        except Exception as e:
            self._error_count += 1
            if self._error_count <= 3 or self._error_count == self._max_errors:
                logging.error(f"InfluxDB write failed ({self._error_count}): {e}")
            if self._error_count >= self._max_errors:
                logging.error("InfluxDB writes disabled after too many failures. "
                              "Restart screen-manager to retry.")

    def close(self):
        """Clean shutdown."""
        if self._client:
            self._client.close()
            logging.info("InfluxDB connection closed")