"""MQTT client management"""
import json
import logging
import threading
import paho.mqtt.client as mqtt
from config.constants import *

class MQTTManager:
    def __init__(self, state, data_logger):
        self.state = state
        self.data_logger = data_logger
        self.client = None
    
    def init_client(self):
        """Initialize MQTT client"""
        self.client = mqtt.Client(client_id="Orion_Publisher", protocol=mqtt.MQTTv311)
        self.client.username_pw_set(username=MQTT_USER, password=MQTT_PASS)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(LOCAL_BROKER, MQTT_PORT, 60)
        self.client.loop_start()
    
    # def start_additional_clients(self):
    #     """Start local and public MQTT clients"""
    #     threading.Thread(target=self._start_client, 
    #                     args=(LOCAL_BROKER, "Local_Client"), daemon=True).start()
    #     threading.Thread(target=self._start_client, 
    #                     args=(PUBLIC_BROKER, "Public_Client"), daemon=True).start()
    
    def _start_client(self, broker, client_name):
        """Start MQTT client for specific broker"""
        client = mqtt.Client(client_id=client_name, protocol=mqtt.MQTTv311)
        
        if broker == LOCAL_BROKER:
            client.username_pw_set(username=MQTT_USER, password=MQTT_PASS)
        
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        
        try:
            client.connect(broker, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            logging.error(f"{client_name} connection failed: {e}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            client.subscribe(TOPIC_ENERGY)
            client.subscribe("pairing/status")
            client.subscribe("orion/wifi_credentials")
            client.subscribe("orion/confirm")
            client.subscribe("orion/scan")
        else:
            logging.error(f"MQTT connection failed: {rc}")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message callback"""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")
            data = json.loads(payload)
            
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
        """Handle energy metrics data"""
        self.state.meter_last_seen = __import__('time').monotonic()
        self.state.energy_data = data
        
        # Log data
        self.data_logger.log_data(data)
        
        # Update metrics
        self.state.energy_metrics.clear()
        self.state.energy_metrics.append(f"Voltage: {data.get('voltage', 'N/A')} V")
        
        tp = data.get("totalPower", None)
        if isinstance(tp, (int, float)):
            self.state.energy_metrics.append(f"Total Power: {tp:.2f} W")
        else:
            self.state.energy_metrics.append(f"Total Power: {tp}")
        
        self.state.energy_metrics.append(f"Energy Total: {data.get('energyTotal', 'N/A')} kWh")
        self.state.energy_metrics.append(f"Runtime: {data.get('runTime', 0)} sec")
        
        # Phases
        phases = data.get("phases", [])
        for idx, phase in enumerate(phases):
            current = phase.get("current", 0.0)
            power = phase.get("power", 0.0)
            self.state.energy_metrics.append(f"Phase {idx+1}: {power:.2f}W / {current:.2f}A")
    
    def _handle_wifi_credentials(self, data):
        """Handle WiFi credentials from ESP32"""
        # This would be handled by WiFi service
        pass
    
    def _handle_confirmation(self, data):
        """Handle confirmation messages"""
        pass
    
    def _handle_scan(self, data):
        """Handle network scan results"""
        with open("scanned_networks.json", "w") as f:
            json.dump(data, f)
    
    def publish(self, topic, message):
        """Publish MQTT message"""
        if self.client:
            self.client.publish(topic, json.dumps(message))