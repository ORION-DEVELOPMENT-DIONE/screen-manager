"""MQTT client management"""
import json
import logging
import threading
import time
import paho.mqtt.client as mqtt
from config.constants import *
from services.influxdb_writer import InfluxDBWriter


class MQTTManager:
    def __init__(self, state, data_logger):
        self.state       = state
        self.data_logger = data_logger
        self.client      = None
        self.influx      = InfluxDBWriter() 

    def init_client(self):
        self.client = mqtt.Client(client_id="Orion_Publisher", protocol=mqtt.MQTTv311)
        self.client.username_pw_set(username=MQTT_USER, password=MQTT_PASS)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(LOCAL_BROKER, MQTT_PORT, 60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(TOPIC_ENERGY)
            client.subscribe("pairing/status")
            client.subscribe("orion/wifi_credentials")
            client.subscribe("orion/confirm")
            client.subscribe("orion/scan")
        else:
            logging.error(f"MQTT connection failed: {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            topic   = msg.topic
            payload = msg.payload.decode("utf-8")
            data    = json.loads(payload)
            logging.info(f"MQTT [{topic}]: {data}")

            if topic == TOPIC_ENERGY:
                self._handle_energy_data(data)
            elif topic == "orion/wifi_credentials":
                self._handle_wifi_credentials(data)
            elif topic == "orion/confirm":
                self._handle_confirmation(data)
            elif topic == "orion/scan":
                self._handle_scan(data)

        except Exception as e:
            logging.error(f"MQTT message error: {e}")

    def _handle_energy_data(self, data):
        """Handle energy metrics — keys match actual ESP32 payload."""
        # Update last-seen timestamp for meter connectivity
        self.state.meter_last_seen = time.monotonic()

        self.state.energy_data = data
        self.data_logger.log_data(data)
        self.influx.write_energy_data(data)

        metrics = []

        # Voltage
        voltage = data.get("voltage")
        if voltage is not None:
            metrics.append(f"Voltage: {voltage:.1f} V")

        # Total power
        total_power = data.get("totalPower")
        if total_power is not None:
            metrics.append(f"Total Power: {total_power:.2f} W")

        # Energy total
        energy_total = data.get("energyTotal")
        if energy_total is not None:
            metrics.append(f"Energy Total: {energy_total:.4f} kWh")

        # Battery
        battery = data.get("battery")
        if battery is not None:
            metrics.append(f"Battery: {battery:.1f} %")

        # Per-phase metrics
        phases = data.get("phases", [])
        for idx, phase in enumerate(phases):
            current = phase.get("current")
            power   = phase.get("power")
            if current is not None and power is not None:
                metrics.append(f"Phase {idx + 1}: {power:.1f} W / {current:.2f} A")

        # Timestamp of last reading
        ts = data.get("timestamp")
        if ts:
            # Show only HH:MM from the timestamp
            try:
                metrics.append(f"Last seen: {ts.split(' ')[1][:5]}")
            except Exception:
                metrics.append(f"Last seen: {ts}")

        self.state.energy_metrics = metrics

    def _handle_wifi_credentials(self, data):
        pass

    def _handle_confirmation(self, data):
        pass

    def _handle_scan(self, data):
        try:
            with open("scanned_networks.json", "w") as f:
                json.dump(data, f)
        except Exception as e:
            logging.error(f"Scan write error: {e}")

    def publish(self, topic, message):
        if self.client:
            self.client.publish(topic, json.dumps(message))