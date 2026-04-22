"""Application constants and configuration"""

# Hardware pins
RST, DC, BL, TP_INT = 6, 25, 22, 9

# Menu states
MENU_MAIN = 0
MENU_MQTT = 1
MENU_METRICS = 3
MENU_WIFI = 2
MENU_CONFIRM_SHUTDOWN = 4
MENU_CONFIRM_NETWORK = 5
MENU_UPDATE = 6
MENU_POWER_OPTIONS = 7
MENU_CONFIRM_RESTART = 8
MENU_CONFIRM_REMOVE_WIFI = 9

# MQTT Settings
LOCAL_BROKER = "localhost"
PUBLIC_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_USER = "orion_device"
MQTT_PASS = "123456789"
TOPIC_ENERGY = "energy/metrics"

# File paths
LOG_FILE = "../logs/mqtt_data_log.txt"
DB_PATH = "../logs/energy_data.db"

# Performance settings
STANDBY_TIMEOUT = 60
GESTURE_DEBOUNCE = 0.25
SCROLL_SPEED = 0.05
RENDER_THROTTLE = 0.02
SSID_CACHE_DURATION = 60

# Display settings
SCREEN_WIDTH = 240
SCREEN_HEIGHT = 240

# UI Settings
MAX_DISPLAY_CHARS = 18
MAX_WRAP_WIDTH = 180

# Gesture codes
GESTURE_UP = 0x01
GESTURE_DOWN = 0x02
GESTURE_RIGHT = 0x03
GESTURE_LEFT = 0x04
GESTURE_TAP = 0x05
GESTURE_LONG_PRESS = 0x0C

# Energy data analysis
ENERGY_HISTORY_24H = []  # Store last 24h of data
ENERGY_HISTORY_7D = []   # Store last 7d of data
MAX_24H_SAMPLES = 288    # 24h * 12 samples/hour (every 5 min)
MAX_7D_SAMPLES = 336     # 7 days * 2 samples/hour (every 30 min)

# Time formats
TIME_FORMAT_SHORT = "%H:%M"
TIME_FORMAT_FULL = "%Y-%m-%d %H:%M:%S"