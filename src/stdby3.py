143#! /usr/bin/python
# -*- coding: UTF-8 -*-
import paho.mqtt.client as mqtt
import signal
import json
import threading
import os
import sys 
print(sys.path)
import time
import logging
import spidev as SPI
import qrcode
import subprocess
import requests
# import qrcode.image.svg
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(parent_dir)
import psutil  # For getting device metrics like CPU usage
from datetime import datetime
from lib import LCD_1inch28, Touch_1inch28
from PIL import Image, ImageDraw, ImageFont
# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')  
# --- Theme and UI Style Definitions ---
class Theme:
    def __init__(self, name, background_path, font_path, font_size, text_color, selected_color):
        self.name = name
        self.background_path = background_path
        self.font = ImageFont.truetype(font_path, font_size)
        self.text_color = text_color
        self.selected_color = selected_color

# Define light and dark themes
THEMES = {
    "light": Theme("light", "../pic/bg_light.jpg", "../Font/DejaVuSans.ttf", 24, "black", "blue"),
    "dark": Theme("dark", "../pic/bg_dark.jpg", "../Font/DejaVuSans.ttf", 24, "white", "cyan"),
}

active_theme = THEMES["dark"]  # Now it's safe to define
logo = Image.open("../pic/dione-logo.jpg").convert("RGB")
emoji_font = ImageFont.truetype("../Font/DejaVuSans.ttf", 24)
TOGGLE_THEME_EMOJI = "🌗"
# Add emoji dictionary for WiFi menu
MENU_EMOJIS = {
    "Energy": "⚡",
    "Device": "📊",  # Try: "●" or "[D]" if this doesn't work
    "WiFi Setup": "📶",  # Try: "≈" or "[W]" if this doesn't work
    "Shutdown": "⏻"
}

WIFI_MENU_EMOJIS = {
    "Pair Devices": "⇄",  # or "↔" or "[P]"
    "Change WiFi": "↻",   # or "⟲" or "[C]"
    "Remove WiFi": "✗",   # or "×" or "[R]"
    "Saved Networks": "≡"  # or "☰" or "[S]"
}
# Constants
RST, DC, BL, TP_INT = 6, 25, 22, 9
MENU_MAIN, MENU_MQTT, MENU_METRICS, MENU_WIFI, MENU_CONFIRM_SHUTDOWN, MENU_CONFIRM_NETWORK  = 0, 1, 3, 2, 4, 5

# MQTT Settings
local_broker = "localhost"
public_broker = "test.mosquitto.org"
port = 1883
mqtt_user = "orion_device"
mqtt_pass = "123456789"     
topic_energy = "energy/metrics"
log_file = "mqtt_data_log.txt"
mqtt_client = None  
# Global Variables
items = ["Energy", "Device", "WiFi Setup", "Shutdown"]
current_menu = MENU_MAIN
selected_option = 0
current_page = 0
energy_metrics = []
wifi_options = ["Pair Devices", "Change WiFi", "Saved Networks", "Remove WiFi"]
wifi_selected = 0

# Scrolling and touch responsiveness variables
last_gesture = None
last_gesture_time = 0
scroll_offset = 0
last_scroll_time = 0
last_selected_network = None
cached_current_ssid = None
last_ssid_check_time = 0
last_render_time = 0

STANDBY_TIMEOUT = 60  # Keep as is or adjust to your preference
GESTURE_DEBOUNCE = 0.25  # Reduced from 0.5 - faster gesture recognition
                        # Lower = more responsive, but risk of double-triggers
                        # Range: 0.2-0.5 seconds

SCROLL_SPEED = 0.05  # Reduced from 0.15 - much faster scrolling
                     # Lower = faster scroll
                     # Range: 0.05-0.2 seconds (0.05 = very fast, 0.2 = slow)

RENDER_THROTTLE = 0.02  # Reduced from 0.05 - smoother scrolling (33 FPS)
                        # Lower = smoother but more CPU usage
                        # Range: 0.02-0.1 (0.02 = 50 FPS, 0.1 = 10 FPS)

SSID_CACHE_DURATION = 60  # Increased from 10 - check less often
                          # Higher = less blocking checks
                          # Range: 10-30 seconds

# Add these global variables at the top with other globals
saved_networks_list = []
saved_networks_selected = 0
in_saved_networks_mode = False
device_metrics_pages = []
last_mqtt_data = None
last_activity_time = time.time()
is_standby = False
in_wifi_qr_mode = False
show_energy_chart = False
chart_mode = 0
energy_data = {}
Mode = 0
Flag = 0

def get_background_copy():
    """Create a completely fresh background image every time"""
    try:
        # Don't cache - reload from disk each time for scrolling scenarios
        # This prevents any memory corruption issues
        with Image.open(active_theme.background_path) as img:
            # Create a new image buffer, don't reuse
            new_img = Image.new("RGB", img.size)
            new_img.paste(img)
            return new_img
    except Exception as e:
        logging.error(f"Error loading background: {e}")
        # Fallback solid color
        if active_theme.name == "dark":
            return Image.new("RGB", (240, 240), color=(0, 0, 0))
        else:
            return Image.new("RGB", (240, 240), color=(255, 255, 255))

def get_font():
    return active_theme.font

def get_text_color():
    return active_theme.text_color

def get_selected_color():
    return active_theme.selected_color

def toggle_theme():
    global active_theme
    active_theme = THEMES["light"] if active_theme.name == "dark" else THEMES["dark"]
    logging.info(f"Toggled theme to {active_theme.name}")

def wrap_text(text, font, max_width):
    lines = []
    words = text.split()
    current_line = ""

    for word in words:
        test_line = current_line + word + " "
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line.strip())
            current_line = word + " "

    if current_line:
        lines.append(current_line.strip())

    return lines

def draw_power_chart(phases):
    if not phases:
        render_message("No phase data")
        return

    image = get_background_copy()
    draw = ImageDraw.Draw(image)

    screen_width, screen_height = image.size
    bar_width = 30
    spacing = 20
    max_bar_height = 100
    origin_y = 180

    max_power = max([p.get("power", 0) for p in phases] + [1])
    total_width = len(phases) * (bar_width + spacing) - spacing
    start_x = (screen_width - total_width) // 2

    # Title
    draw.text((60, 10), "Power(W)", fill=get_text_color(), font=get_font())

    bar_colors = ["red", "green", "blue"]

    for i, phase in enumerate(phases):
        power = phase.get("power", 0)
        bar_height = int((power / max_power) * max_bar_height)

        x = start_x + i * (bar_width + spacing)
        y = origin_y - bar_height

        # Draw bar
        draw.rectangle([x, y, x + bar_width, origin_y], fill=bar_colors[i % len(bar_colors)])

        # Draw power value above
        value_text = f"{int(power)}"
        value_w = get_font().getlength(value_text)
        draw.text((x + (bar_width - value_w) // 2, y - 18), value_text, fill=get_text_color(), font=get_font())

        # Phase label below
        label = f"P{i+1}"
        label_w = get_font().getlength(label)
        draw.text((x + (bar_width - label_w) // 2, origin_y + 5), label, fill=get_text_color(), font=get_font())

    disp.ShowImage(image)

def ensure_orion_connection():
    """
    Simplified pairing flow - ESP32 validates credentials first.
    OrangePi waits indefinitely while connected to OrionSetup.
    """
    try:
        # ========== PHASE 1: CONNECT TO ORIONSETUP ==========
        render_message("Checking connection...")
        result = subprocess.run(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                              capture_output=True, text=True, timeout=5)
        
        already_connected = False
        for line in result.stdout.split('\n'):
            if line.startswith('yes:') and 'OrionSetup' in line:
                already_connected = True
                break

        if not already_connected:
            render_message("Scanning networks...")
            subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'],
                          timeout=30, stderr=subprocess.DEVNULL)
            time.sleep(2)

            result = subprocess.run(['nmcli', '-t', '-f', 'ssid', 'dev', 'wifi'],
                                  capture_output=True, text=True, timeout=5)

            if 'OrionSetup' not in result.stdout:
                return (False, "Energy Meter not found")

            render_message("Connecting to\nOrionSetup...")
            connect_result = subprocess.run([
                'sudo', 'nmcli', 'dev', 'wifi', 'connect', 'OrionSetup',
                'password', 'Orion2025'
            ], capture_output=True, text=True, timeout=60)

            if connect_result.returncode != 0:
                return (False, "Connection failed")
            
            render_message("Connected to\nOrionSetup!")
            time.sleep(2)
        
        # ========== PHASE 2: WAIT INDEFINITELY FOR CREDENTIALS ==========
        # render_message("Waiting for\nuser to submit\nWiFi credentials...")
        logging.info("Waiting for validated credentials from ESP32 (no timeout)")
        
        POLL_INTERVAL = 3  # Check every 3 seconds
        poll_count = 0
        
        while True:  # ✅ INFINITE LOOP - only exits when credentials received
            try:
                # ✅ Verify we're still connected to OrionSetup
                check_result = subprocess.run(
                    ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                    capture_output=True, text=True, timeout=5
                )
                
                still_connected = False
                for line in check_result.stdout.split('\n'):
                    if line.startswith('yes:') and 'OrionSetup' in line:
                        still_connected = True
                        break
                
                if not still_connected:
                    logging.warning("Disconnected from OrionSetup")
                    render_message("⚠️ Disconnected\nfrom OrionSetup")
                    time.sleep(2)
                    return (False, "Lost connection to OrionSetup")
                
                # ✅ Poll for credentials
                response = requests.get('http://192.168.4.1:8080/credentials', timeout=3)
                
                if response.status_code == 200:
                    data = response.json()
                    ssid = data.get('ssid')
                    password = data.get('password')
                    validated = data.get('validated', False)
                    
                    if ssid and validated:
                        logging.info(f"✅ Received PRE-VALIDATED credentials: SSID={ssid}")
                        render_message(f"Received:\n{ssid}\n\nConnecting...")
                        time.sleep(1)
                        
                        # ========== PHASE 3: CONNECT TO NEW WIFI ==========
                        # Delete old connection
                        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', ssid],
                                     capture_output=True, check=False)
                        time.sleep(0.5)
                        
                        # Connect directly (credentials already validated by ESP32)
                        connect_result = subprocess.run([
                            'sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid,
                            'password', password
                        ], capture_output=True, text=True, timeout=60)
                        
                        if connect_result.returncode == 0:
                            render_message(f"Connected to\n{ssid}!")
                            time.sleep(2)
                            render_message("Setup complete!")
                            time.sleep(2)
                            return (True, "✅ Pairing complete!")
                        else:
                            # Should not happen since ESP32 validated
                            logging.error(f"Unexpected connection failure: {connect_result.stderr}")
                            render_message("Connection\nfailed")
                            time.sleep(2)
                            
                            # Reconnect to OrionSetup
                            subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect', 
                                          'OrionSetup', 'password', 'Orion2025'],
                                         capture_output=True, timeout=30)
                            return (False, "Connection failed")
            
            except requests.exceptions.Timeout:
                # Expected - ESP32 hasn't served credentials yet
                pass
            except requests.exceptions.ConnectionError:
                # Expected - HTTP server not ready yet
                pass
            except Exception as e:
                logging.error(f"Poll error: {e}")
            
            # ✅ Update UI periodically (every 15 seconds)
            poll_count += 1
            if poll_count % 5 == 0:  # Every 15 seconds (5 polls × 3s)
                elapsed_mins = (poll_count * POLL_INTERVAL) // 60
                # render_message(f"Waiting...\n{elapsed_mins} min elapsed\n\nReady to receive\nWiFi credentials")
                time.sleep(2)
            time.sleep(POLL_INTERVAL)

    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return (False, "Unexpected error")

def draw_line_chart(values):
    if not values or len(values) < 2:
        render_message("No data for line chart")
        return

    image = get_background_copy()
    draw = ImageDraw.Draw(image)

    max_val = max(values)
    min_val = min(values)
    chart_height = 140
    chart_top = 40
    chart_bottom = chart_top + chart_height
    chart_width = 200
    chart_left = 20

    scale = chart_height / (max_val - min_val + 1e-3)

    # Title
    title = "Current per Phase"
    draw.text((60, 10), title, fill=get_text_color(), font=get_font())

    # Draw X-Y axis
    draw.line([(chart_left, chart_top), (chart_left, chart_bottom)], fill="gray")
    draw.line([(chart_left, chart_bottom), (chart_left + chart_width, chart_bottom)], fill="gray")

    colors = ["red", "green", "blue"]  # For up to 3 phases

    for i in range(1, len(values)):
        x1 = chart_left + (i - 1) * (chart_width // (len(values) - 1))
        y1 = chart_bottom - int((values[i - 1] - min_val) * scale)
        x2 = chart_left + i * (chart_width // (len(values) - 1))
        y2 = chart_bottom - int((values[i] - min_val) * scale)

        draw.line([x1, y1, x2, y2], fill=colors[i % len(colors)], width=2)

    disp.ShowImage(image)

def Int_Callback(TP_INT=TP_INT):
    global Mode, Flag
    if Mode == 1:
        Flag = 1
        touch.get_point()
    else:
        touch.Gestures = touch.Touch_Read_Byte(0x01)
    
    global last_activity_time
    last_activity_time = time.time()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        # logging.info(f"Connected to MQTT broker with code {rc}")
        client.subscribe(topic_energy)
        client.subscribe("pairing/status")
        client.subscribe("orion/wifi_credentials")  # ✅ Subscribe to WiFi credentials
        client.subscribe("orion/confirm")
        client.subscribe("orion/scan")
    else:
        logging.error(f"Failed to connect to MQTT broker: code {rc}")

def on_message(client, userdata, msg):
    global current_page, energy_metrics, energy_data

    try:
        topic = msg.topic
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        logging.info(f"MQTT topic [{topic}]: {data}")

        if topic == "energy/metrics":
            energy_data = data
            energy_metrics.clear()
            draw_power_chart(energy_data.get("phases", []))

            # Basic Info
            energy_metrics.append(f"Voltage: {data.get('voltage', 'N/A')} V")
            tp = data.get("totalPower", None)
            energy_metrics.append(f"Total Power: {tp:.2f} W" if isinstance(tp, (int, float)) else f"Total Power: {tp}")
            energy_metrics.append(f"Energy Total: {data.get('energyTotal', 'N/A')} kWh")
            energy_metrics.append(f"Runtime: {data.get('runTime', 0)} sec")

            # Phases (nested)
            phases = data.get("phases", [])
            for idx, phase in enumerate(phases):
                current = phase.get("current", 0.0)
                power = phase.get("power", 0.0)
                energy_metrics.append(f"Phase {idx+1}: {power:.2f}W / {current:.2f}A")

            render_page(current_page)
        elif topic == "orion/wifi_credentials":
            # Received WiFi credentials from ESP32
            ssid = data.get("ssid")
            password = data.get("password")
            if ssid:
                render_message(f"Connecting to\n{ssid}...")
                try:
                    result = subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 
                                  'password', password], capture_output=True, text=True, timeout=60)

                    if result.returncode == 0:
                        render_message("✅ WiFi Connected!")
                        time.sleep(3)
                        
                        try:
                            mqtt_client.loop_stop()
                            mqtt_client.disconnect()
                            time.sleep(1)
                            
                            # Reconnect to local broker
                            mqtt_client.connect(local_broker, port, 60)
                            mqtt_client.loop_start()
                            time.sleep(1)
                            
                            # Publish confirmation
                            mqtt_client.publish("pairing/status", json.dumps({"status": "wifi_configured"}))
                            logging.info("Published wifi_configured confirmation")
                            
                            render_message("✅ Setup complete!")
                            time.sleep(2)
                            render_main_menu()
                        except Exception as mqtt_error:
                            logging.error(f"MQTT reconnection error: {mqtt_error}")
                            render_message("✅ WiFi connected\nbut MQTT failed")
                            time.sleep(3)
                            render_main_menu()      
                    else:
                        render_message("❌ WiFi failed\nCheck password")
                        mqtt_client.publish("pairing/status", json.dumps({"status": "connection_failed"}))
                        logging.error(f"WiFi error: {result.stderr}")
                        time.sleep(3)
                        render_wifi_setup_menu()
                except Exception as e:
                    render_message("❌ Connection error")
                    logging.error(f"WiFi connection error: {e}")
                    time.sleep(3)
                    render_wifi_setup_menu()

        elif topic == "orion/confirm":
            render_message("✅ Wi-Fi Connected!" if data.get("status") == "success" else "❌ Wi-Fi Failed")

        elif topic == "orion/scan":
            with open("scanned_networks.json", "w") as f:
                json.dump(data, f)
            render_message("📶 Scan received. Use web UI.")

    except Exception as e:
        logging.error(f"MQTT on_message error: {e}")

def log_received_data(data):
    try:
        with open(log_file, "a") as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"{timestamp} - Received: {json.dumps(data)}\n")
    except Exception as e:
        logging.error(f"Error logging data: {e}")

def start_mqtt_client(broker, client_name):
    client = mqtt.Client(client_id=client_name, protocol=mqtt.MQTTv311)
    # ✅ Add authentication for all clients
    if broker == local_broker:  # Only authenticate for local broker
        client.username_pw_set(username="orion_device", password="123456789")
    
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(broker, port, 60)
        client.loop_forever()
    except Exception as e:
        logging.error(f"{client_name} connection failed: {e}")

def start_mqtt():
    threading.Thread(target=start_mqtt_client, args=(local_broker, "Local_Client")).start()
    threading.Thread(target=start_mqtt_client, args=(public_broker, "Public_Client")).start()

def render_page(index):
    image = get_background_copy()
    draw = ImageDraw.Draw(image)

    if chart_mode == 0:  # Scroll text
        if not energy_metrics:
            render_message("No energy metrics to display")
            return
        index %= len(energy_metrics)
        lines = wrap_text(energy_metrics[index], get_font(), 220)
        y = 80
        for line in lines:
            draw.text((20, y), line, fill=get_text_color(), font=get_font())
            y += 30

        # Arrows
        screen_width, screen_height = image.size
        arrow_x = screen_width // 2 - 10
        draw.text((arrow_x, 10), "▲", fill=get_selected_color(), font=get_font())
        draw.text((arrow_x, screen_height - 30), "▼", fill=get_selected_color(), font=get_font())

        disp.ShowImage(image)

    elif chart_mode == 1:  # Bar chart
        draw_power_chart(energy_data.get("phases", []))  # You already have this function

    elif chart_mode == 2:  # Line chart (e.g. current values)
        currents = [p.get("current", 0) for p in energy_data.get("phases", [])]
        draw_line_chart(currents)

def render_menu(options, selected_index, theme=active_theme):
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size

    height = len(options) * 40
    y_start = (screen_height - height) // 2

    for i, option in enumerate(options):
        emoji = MENU_EMOJIS.get(option, '')
        label = option
        color = get_selected_color() if i == selected_index else get_text_color()

        # Draw emoji separately (left-aligned)
        emoji_x = 30
        draw.text((emoji_x, y_start + i * 40), emoji, fill=color, font=emoji_font)

        # Draw label next to emoji
        label_x = emoji_x + 30  # spacing between emoji and label
        draw.text((label_x, y_start + i * 40), label, fill=color, font=theme.font)

    disp.ShowImage(image)

def render_main_menu():
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size

    height = len(items) * 40
    y_start = (screen_height - height) // 2

    for i, item in enumerate(items):
        prefix = "➤ " if i == selected_option else "  "
        text = prefix + item
        color = get_selected_color() if i == selected_option else get_text_color()
        w = get_font().getlength(text)
        draw.text(((screen_width - w) // 2, y_start + i * 40), text, fill=color, font=get_font())

    # Theme toggle emoji (or any icon) – still centered at bottom
    emoji_w = get_font().getlength(TOGGLE_THEME_EMOJI)
    draw.text(((screen_width - emoji_w) // 2, screen_height - 35), TOGGLE_THEME_EMOJI, fill=get_selected_color(), font=get_font())

    disp.ShowImage(image)


def render_confirmation():
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size

    # Message centered
    msg = "Shutdown?"
    w = get_font().getlength(msg)
    draw.text(((screen_width - w) // 2, 50), msg, fill=get_text_color(), font=get_font())

    # Box dimensions
    box_w, box_h = 90, 50
    box_y = 120
    spacing = 20
    total_width = 2 * box_w + spacing
    start_x = (screen_width - total_width) // 2

    # Draw NO box
    draw.rectangle([start_x, box_y, start_x + box_w, box_y + box_h], outline=get_selected_color(), width=2)
    no_text = "No"
    no_w = get_font().getlength(no_text)
    draw.text((start_x + (box_w - no_w) // 2, box_y + 10), no_text, fill=get_selected_color(), font=get_font())

    # Draw YES box
    draw.rectangle([start_x + box_w + spacing, box_y, start_x + 2 * box_w + spacing, box_y + box_h], outline=get_text_color(), width=2)
    yes_text = "Yes"
    yes_w = get_font().getlength(yes_text)
    draw.text((start_x + box_w + spacing + (box_w - yes_w) // 2, box_y + 10), yes_text, fill=get_text_color(), font=get_font())

    disp.ShowImage(image)


def handle_shutdown_menu(gesture):
    global current_menu
    if gesture == 0x0C:  # Long press = cancel
        current_menu = MENU_MAIN
        render_main_menu()
    
    elif gesture == 0x05:  # Tap detected
        touch.get_point()
        x, y = touch.X_point, touch.Y_point

        box_w, box_h = 90, 50
        box_y = 120
        spacing = 20
        start_x = (240 - (2 * box_w + spacing)) // 2

        # NO box
        if start_x <= x <= start_x + box_w and box_y <= y <= box_y + box_h:
            current_menu = MENU_MAIN
            render_main_menu()
        # YES box
        elif start_x + box_w + spacing <= x <= start_x + 2 * box_w + spacing and box_y <= y <= box_y + box_h:
            render_message("Shutting down...")
            time.sleep(2)
            os.system("sudo shutdown now")

def update_device_metrics_loop():
    global device_metrics_pages
    while True:
        if not is_standby:
            device_metrics_pages = get_device_metrics()
        time.sleep(5)

def get_device_metrics():
    cpu = psutil.cpu_percent(interval=0.1)  # Reduced interval for faster response
    mem = psutil.virtual_memory().percent
    uptime = time.time() - psutil.boot_time()
    try:
        ip_addr = os.popen("hostname -I").read().strip().split()[0]
    except:
        ip_addr = "N/A"
    try:
        ssid = os.popen("iwgetid -r").read().strip() or \
               os.popen("nmcli -t -f active,ssid dev wifi | egrep '^yes' | cut -d\\: -f2").read().strip() or "N/A"
    except:
        ssid = "N/A"
    return [
        f"CPU Usage: {cpu}%",
        f"Memory Usage: {mem}%",
        f"Uptime: {time.strftime('%H:%M:%S', time.gmtime(uptime))}",
        f"WiFi SSID: {ssid}",
        f"IP Address: {ip_addr}"
    ]

def render_wifi_qr_code():
    """Display QR code with URL text below - optimized for 240x240 round screen"""
    url = "http://orion.local:3000"
    qr = qrcode.make(url)
    
    image = get_background_copy()
    
    # QR code sizing - leave room for text
    qr_size = 160
    qr_resized = qr.resize((qr_size, qr_size))
    
    # Center QR code horizontally, position higher to make room for URL
    qr_x = (240 - qr_size) // 2
    qr_y = 20
    image.paste(qr_resized, (qr_x, qr_y))
    
    draw = ImageDraw.Draw(image)
    
    # Draw URL below QR code with smaller font if needed
    url_font = ImageFont.truetype("../Font/DejaVuSans.ttf", 16)
    url_w = url_font.getlength(url)
    
    # Center URL below QR code
    url_x = (240 - url_w) // 2
    url_y = qr_y + qr_size + 10
    
    draw.text((url_x, url_y), url, fill=get_selected_color(), font=url_font)
    
    disp.ShowImage(image)
    logging.info("Displayed web portal QR code with URL")

def render_wifi_setup_menu():
    """Enhanced WiFi menu with emojis as selection indicators"""
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size

    height = len(wifi_options) * 40
    y_start = (screen_height - height) // 2

    for i, item in enumerate(wifi_options):
        is_selected = (i == wifi_selected)
        color = get_selected_color() if is_selected else get_text_color()
        
        # Get the emoji for this menu item
        emoji = WIFI_MENU_EMOJIS.get(item, '')
        
        # Calculate positions for centered layout
        # Emoji on the left, text next to it
        emoji_x = 40
        text_x = emoji_x + 30  # Space between emoji and text
        
        y_pos = y_start + i * 40
        
        # Draw emoji with selection color
        draw.text((emoji_x, y_pos), emoji, fill=color, font=emoji_font)
        
        # Draw menu item text
        draw.text((text_x, y_pos), item, fill=color, font=get_font())

    disp.ShowImage(image)

def disconnect_wifi():
    """Disconnect and remove current WiFi connection"""
    try:
        current = get_current_ssid()
        if current:
            subprocess.run(['sudo', 'nmcli', 'connection', 'delete', current], timeout=10)
            render_message(f"Removed {current}")
            mqtt_client.publish("pairing/status", json.dumps({"status": "disconnected"}))
            return True
    except Exception as e:
        logging.error(f"Error disconnecting WiFi: {e}")
    return False

def get_saved_networks():
    """Get list of saved WiFi networks"""
    try:
        result = subprocess.run(['nmcli', '-t', '-f', 'NAME', 'connection', 'show'],
                              capture_output=True, text=True, timeout=5)
        networks = [line.strip() for line in result.stdout.split('\n') if line.strip()]
        # Filter out non-WiFi connections
        wifi_networks = []
        for network in networks:
            check = subprocess.run(['nmcli', '-t', '-f', 'connection.type', 'connection', 'show', network],
                                 capture_output=True, text=True, timeout=2)
            if '802-11-wireless' in check.stdout:
                wifi_networks.append(network)
        return wifi_networks
    except Exception as e:
        logging.error(f"Error getting saved networks: {e}")
        return []

def get_current_ssid():
    """Get currently connected SSID with caching to avoid blocking"""
    global cached_current_ssid, last_ssid_check_time
    
    current_time = time.time()
    
    # Return cached value if recent
    if cached_current_ssid is not None and (current_time - last_ssid_check_time) < SSID_CACHE_DURATION:
        return cached_current_ssid
    
    # Try to get fresh SSID (non-blocking with short timeout)
    try:
        result = subprocess.run(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'], 
                              capture_output=True, text=True, timeout=1)  # Very short timeout
        for line in result.stdout.split('\n'):
            if line.startswith('yes:'):
                ssid = line.split(':', 1)[1].strip()
                cached_current_ssid = ssid
                last_ssid_check_time = current_time
                return ssid
        # No active connection found
        cached_current_ssid = None
        last_ssid_check_time = current_time
        return None
    except subprocess.TimeoutExpired:
        # Keep using old cached value if available
        logging.debug("SSID check timed out, using cached value")
        return cached_current_ssid
    except Exception as e:
        logging.error(f"Error getting current SSID: {e}")
        return cached_current_ssid

def render_saved_networks():
    """Optimized rendering with throttling"""
    global saved_networks_list, saved_networks_selected, scroll_offset, last_scroll_time, last_selected_network
    global last_render_time
    
    current_time = time.time()
    
    # Throttle rendering for performance
    if current_time - last_render_time < RENDER_THROTTLE:
        return True
    
    last_render_time = current_time
    
    if not saved_networks_list:
        saved_networks_list = get_saved_networks()
        saved_networks_selected = 0
    
    if not saved_networks_list:
        render_message("No saved\nnetworks found")
        time.sleep(2)
        return False
    
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    
    # Title
    title = "Saved Networks"
    title_font = ImageFont.truetype("../Font/DejaVuSans.ttf", 18)
    title_w = title_font.getlength(title)
    draw.text(((240 - title_w) // 2, 30), title, fill=get_selected_color(), font=title_font)
    
    # Use cached SSID
    current = get_current_ssid()
    
    network_font = ImageFont.truetype("../Font/DejaVuSans.ttf", 20)
    
    display_count = 4
    item_spacing = 32
    
    start_idx = max(0, saved_networks_selected - 1)
    end_idx = min(len(saved_networks_list), start_idx + display_count)
    
    y_start = 60
    current_y = y_start
    
    selected_network = saved_networks_list[saved_networks_selected]
    
    # Reset scroll if selection changed
    if selected_network != last_selected_network:
        scroll_offset = 0
        last_scroll_time = current_time
        last_selected_network = selected_network
    
    for i in range(start_idx, end_idx):
        network = saved_networks_list[i]
        is_current = (current is not None and network == current)
        is_selected = (i == saved_networks_selected)
        
        color = get_selected_color() if is_selected else get_text_color()
        
        if is_selected:
            prefix = "➤ "
            suffix = " ✓" if is_current else ""
            
            max_chars = 18
            
            if len(network) > max_chars:
                # Scrolling text
                display_network = network + "  ...  " + network[:10]
                
                if current_time - last_scroll_time > SCROLL_SPEED:
                    scroll_offset = (scroll_offset + 1) % (len(network) + 7)
                    last_scroll_time = current_time
                
                visible_text = display_network[scroll_offset:scroll_offset + max_chars]
                text = prefix + visible_text + suffix
            else:
                text = prefix + network + suffix
                scroll_offset = 0
            
            draw.text((10, current_y), text, fill=color, font=network_font)
            current_y += item_spacing
        else:
            prefix = "  "
            suffix = " ✓" if is_current else ""
            display_name = network[:17] if len(network) > 17 else network
            text = f"{prefix}{display_name}{suffix}"
            
            draw.text((10, current_y), text, fill=color, font=network_font)
            current_y += item_spacing
    
    if len(saved_networks_list) > display_count:
        scroll_font = ImageFont.truetype("../Font/DejaVuSans.ttf", 14)
        scroll_text = "▲▼"
        scroll_w = scroll_font.getlength(scroll_text)
        draw.text(((240 - scroll_w) // 2, 190), scroll_text, fill=get_selected_color(), font=scroll_font)
    
    instruction_font = ImageFont.truetype("../Font/DejaVuSans.ttf", 14)
    instruction_text = "Tap=Connect"
    instruction_w = instruction_font.getlength(instruction_text)
    draw.text(((240 - instruction_w) // 2, 210), instruction_text, fill="gray", font=instruction_font)
    
    disp.ShowImage(image)
    return True

def render_network_confirmation(network_name):
    """Render confirmation dialog for network connection with scrolling support"""
    global scroll_offset, last_scroll_time, last_selected_network
    
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size

    # Message centered - with network name
    msg_font = ImageFont.truetype("../Font/DejaVuSans.ttf", 18)
    msg1 = "Connect to:"
    msg1_w = msg_font.getlength(msg1)
    draw.text(((screen_width - msg1_w) // 2, 30), msg1, fill=get_text_color(), font=msg_font)
    
    # Network name with scrolling if too long
    net_font = ImageFont.truetype("../Font/DejaVuSans.ttf", 18)  # Slightly smaller for long names
    max_chars = 20  # Max characters that fit
    
    # Reset scroll if this is a new network
    current_time = time.time()
    if network_name != last_selected_network:
        scroll_offset = 0
        last_scroll_time = current_time
        last_selected_network = network_name
    
    if len(network_name) > max_chars:
        # Network name needs scrolling
        display_network = network_name + "  ...  " + network_name[:10]
        
        # Update scroll position
        if current_time - last_scroll_time > SCROLL_SPEED:
            scroll_offset = (scroll_offset + 1) % (len(network_name) + 7)
            last_scroll_time = current_time
        
        network_display = display_network[scroll_offset:scroll_offset + max_chars]
    else:
        # Fits without scrolling
        network_display = network_name
        scroll_offset = 0
    
    # Draw network name (centered)
    net_w = net_font.getlength(network_display)
    draw.text(((screen_width - net_w) // 2, 55), network_display, fill=get_selected_color(), font=net_font)

    # Question mark
    msg2 = "?"
    msg2_w = msg_font.getlength(msg2)
    draw.text(((screen_width - msg2_w) // 2, 80), msg2, fill=get_text_color(), font=msg_font)

    # Box dimensions
    box_w, box_h = 90, 50
    box_y = 130
    spacing = 20
    total_width = 2 * box_w + spacing
    start_x = (screen_width - total_width) // 2

    # Draw NO box
    draw.rectangle([start_x, box_y, start_x + box_w, box_y + box_h], outline=get_text_color(), width=2)
    no_text = "No"
    no_font = get_font()
    no_w = no_font.getlength(no_text)
    draw.text((start_x + (box_w - no_w) // 2, box_y + 12), no_text, fill=get_text_color(), font=no_font)

    # Draw YES box
    draw.rectangle([start_x + box_w + spacing, box_y, start_x + 2 * box_w + spacing, box_y + box_h], 
                   outline=get_selected_color(), width=2)
    yes_text = "Yes"
    yes_w = no_font.getlength(yes_text)
    draw.text((start_x + box_w + spacing + (box_w - yes_w) // 2, box_y + 12), yes_text, 
              fill=get_selected_color(), font=no_font)

    disp.ShowImage(image)
    del draw
    del image

def handle_network_confirmation(gesture):
    """Handle network confirmation with scrolling support"""
    global current_menu, network_to_connect, in_saved_networks_mode, saved_networks_list
    
    # Continuously update for scrolling animation (if no gesture)
    if gesture == 0:
        render_network_confirmation(network_to_connect)
        return
    
    if gesture == 0x0C:  # Long press = cancel
        current_menu = MENU_WIFI
        in_saved_networks_mode = True
        render_saved_networks()
    
    elif gesture == 0x05:  # Tap detected
        touch.get_point()
        x, y = touch.X_point, touch.Y_point

        box_w, box_h = 90, 50
        box_y = 130
        spacing = 20
        start_x = (240 - (2 * box_w + spacing)) // 2

        # NO box
        if start_x <= x <= start_x + box_w and box_y <= y <= box_y + box_h:
            current_menu = MENU_WIFI
            in_saved_networks_mode = True
            render_saved_networks()
            time.sleep(0.2)
        # YES box
        elif start_x + box_w + spacing <= x <= start_x + 2 * box_w + spacing and box_y <= y <= box_y + box_h:
            if connect_to_saved_network(network_to_connect):
                mqtt_client.publish("pairing/status", json.dumps({"status": "wifi_changed"}))
            in_saved_networks_mode = False
            saved_networks_list = []
            current_menu = MENU_WIFI
            render_wifi_setup_menu()
            time.sleep(0.2)

def render_loading_animation(message, duration=3):
    """Show animated loading message"""
    start_time = time.time()
    dots = 0
    
    while time.time() - start_time < duration:
        dot_str = "." * (dots % 4)
        render_message(f"{message}{dot_str}")
        time.sleep(0.5)
        dots += 1

def connect_to_saved_network(network_name):
    """Connect to a saved network"""
    try:
        render_message(f"Connecting to\n{network_name}...")
        
        result = subprocess.run(['sudo', 'nmcli', 'connection', 'up', network_name],
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            render_message(f"✅ Connected to\n{network_name}")
            time.sleep(2)
            return True
        else:
            render_message(f"❌ Failed to\nconnect to\n{network_name}")
            logging.error(f"Connection error: {result.stderr}")
            time.sleep(2)
            return False
    except Exception as e:
        render_message("❌ Connection\nerror")
        logging.error(f"Error connecting: {e}")
        time.sleep(2)
        return False

def handle_wifi_setup_menu(gesture):
    """Handle WiFi setup menu - don't clear gestures here, already cleared in main loop"""
    global wifi_selected, current_menu, in_wifi_qr_mode
    global saved_networks_list, saved_networks_selected, in_saved_networks_mode
    global network_to_connect, last_gesture

    # Handle saved networks mode
    if in_saved_networks_mode:
        if not saved_networks_list:
            in_saved_networks_mode = False
            render_wifi_setup_menu()
            return
        
        if gesture == 0:
            return
        elif gesture == 0x01:  # UP
            saved_networks_selected = (saved_networks_selected - 1) % len(saved_networks_list)
            render_saved_networks()
        elif gesture == 0x02:  # DOWN
            saved_networks_selected = (saved_networks_selected + 1) % len(saved_networks_list)
            render_saved_networks()
        elif gesture == 0x05:  # SELECT
            network_to_connect = saved_networks_list[saved_networks_selected]
            current_menu = MENU_CONFIRM_NETWORK
            in_saved_networks_mode = False
            render_network_confirmation(network_to_connect)
            time.sleep(0.2)
        elif gesture in [0x04, 0x0C]:  # BACK
            in_saved_networks_mode = False
            saved_networks_list = []
            current_menu = MENU_WIFI  # Stay in wifi menu
            render_wifi_setup_menu()
            time.sleep(0.2)
        return

    # Handle QR code mode
    if in_wifi_qr_mode:
        if gesture == 0x04:  # LEFT
            in_wifi_qr_mode = False
            current_menu = MENU_WIFI
            render_wifi_setup_menu()
            time.sleep(0.2)
        elif gesture == 0x0C:  # LONG PRESS (already handled in main loop)
            pass
        return

    # Normal WiFi menu navigation
    if gesture == 0x01:  # UP
        wifi_selected = (wifi_selected - 1) % len(wifi_options)
        render_wifi_setup_menu()
    elif gesture == 0x02:  # DOWN
        wifi_selected = (wifi_selected + 1) % len(wifi_options)
        render_wifi_setup_menu()
    elif gesture == 0x05:  # SELECT
        time.sleep(0.1)
        
        if wifi_selected == 0:  # Pair Devices
            mqtt_client.publish("pairing/status", json.dumps({"status": "starting"}))
            render_loading_animation("Pairing", 2)
            
            success, message = ensure_orion_connection()
            render_message(message)
            
            if success:
                mqtt_client.publish("pairing/status", json.dumps({"status": "paired"}))
            else:
                mqtt_client.publish("pairing/status", json.dumps({"status": "failed"}))
            
            time.sleep(2)
            render_wifi_setup_menu()
            
        elif wifi_selected == 1:  # Change WiFi
            render_message("Triggering\nAP mode...")
            mqtt_client.publish("orion/trigger", json.dumps({"action": "enter_ap_mode"}))
            render_loading_animation("Switching", 8)
            
            success, message = ensure_orion_connection()
            render_message(message)
            
            if success:
                mqtt_client.publish("pairing/status", json.dumps({"status": "ready_to_configure"}))
            
            time.sleep(2)
            render_wifi_setup_menu()
            
        elif wifi_selected == 2:  # Saved Networks
            in_saved_networks_mode = True
            saved_networks_list = get_saved_networks()
            saved_networks_selected = 0
            if not render_saved_networks():
                in_saved_networks_mode = False
                render_wifi_setup_menu()
            time.sleep(0.2)
                
        elif wifi_selected == 3:  # Remove WiFi
            current = get_current_ssid_cached()
            if current:
                render_message(f"Removing\n{current}...")
                if disconnect_wifi():
                    render_message("✅ WiFi removed")
                else:
                    render_message("❌ Failed to\nremove")
            else:
                render_message("No active\nconnection")
            time.sleep(2)
            render_wifi_setup_menu()
            
    elif gesture in [0x04, 0x0C]:  # LEFT or BACK
        current_menu = MENU_MAIN
        render_main_menu()
        time.sleep(0.1)  # Longer delay when going back
        
def render_device_metrics():
    global current_page
    if not device_metrics_pages:
        logging.warning("Device metrics not available yet.")
        render_message("Loading device metrics...")
        return

    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    text = device_metrics_pages[current_page % len(device_metrics_pages)]
    lines = wrap_text(text, get_font(), max_width=220)
    y = 80
    for line in lines:
        draw.text((20, y), line, fill=get_text_color(), font=get_font())
        y += 30

    # Centered scroll arrows
    screen_width, screen_height = image.size
    arrow_x = screen_width // 2 - 10
    draw.text((arrow_x, 10), "▲", fill=get_selected_color(), font=get_font())
    draw.text((arrow_x, screen_height - 30), "▼", fill=get_selected_color(), font=get_font())
    

    disp.ShowImage(image)
    logging.info("Rendered device metrics")

def render_mqtt_data():
    if not energy_metrics:
        render_message("No MQTT Data")
    else:
        render_page(current_page)

def render_message(message, font_size=24):
    """Enhanced message rendering with better text sizing for round screen"""
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    
    # Use smaller font for longer messages
    if len(message) > 50:
        font = ImageFont.truetype("../Font/DejaVuSans.ttf", 18)
    elif len(message) > 30:
        font = ImageFont.truetype("../Font/DejaVuSans.ttf", 20)
    else:
        font = ImageFont.truetype("../Font/DejaVuSans.ttf", font_size)
    
    lines = message.split('\n')
    all_lines = []
    
    # Adjust wrap width for round screen (smaller usable area)
    max_width = 180  # Reduced from 200 for better round screen fit
    
    for line in lines:
        if line.strip():  # Skip empty lines
            wrapped = wrap_text(line, font, max_width=max_width)
            all_lines.extend(wrapped)
        else:
            all_lines.append("")  # Preserve intentional line breaks
    
    # Dynamic line height based on font size
    line_height = font_size + 4
    total_height = len(all_lines) * line_height
    
    # Center vertically with slight upward bias for round screen
    y_start = max(30, (240 - total_height) // 2 - 10)
    
    for i, line in enumerate(all_lines):
        if line:  # Only draw non-empty lines
            line_w = font.getlength(line)
            x = (240 - line_w) // 2
            y = y_start + (i * line_height)
            draw.text((x, y), line, fill=get_text_color(), font=font)
    
    disp.ShowImage(image)
    logging.info(f"Rendered message: {message[:50]}...")

def lcd_sleep():
    logging.info("Putting display to sleep.")
    disp.LCD_WriteReg(0x28)  # Display OFF
    disp.LCD_WriteReg(0x10)  # Enter SLEEP mode

def lcd_wake():
    logging.info("Waking display from sleep.")
    disp.LCD_WriteReg(0x11)  # Exit SLEEP mode
    time.sleep(0.12)
    disp.LCD_WriteReg(0x29)  # Display ON

def handle_mqtt_menu(gesture):
    global current_page, current_menu, energy_metrics, show_energy_chart,chart_mode

    if not energy_metrics:
        logging.info("No MQTT data available. Only BACK gesture allowed.")
        if gesture in [0x04, 0x0C]:  # BACK or LEFT
            current_menu = MENU_MAIN
            render_main_menu()
        return

    if gesture == 0x01:  # UP
        current_page = (current_page - 1) % len(energy_metrics)
        render_page(current_page)
    elif gesture == 0x02:  # DOWN
        current_page = (current_page + 1) % len(energy_metrics)
        render_page(current_page)
    elif gesture == 0x05:  # TAP 
        chart_mode = (chart_mode + 1) % 3  # Cycle through 0, 1, 2
        render_page(current_page)
    elif gesture in [0x04, 0x0C]:  # BACK
        current_menu = MENU_MAIN
        show_energy_chart = False  # reset
        render_main_menu()

def handle_device_metrics_menu(gesture):
    global current_page, current_menu, device_metrics_pages

    if not device_metrics_pages:
        device_metrics_pages = get_device_metrics()

    if gesture == 0x01:  # UP
        current_page = (current_page - 1) % len(device_metrics_pages)
        render_device_metrics()
    elif gesture == 0x02:  # DOWN
        current_page = (current_page + 1) % len(device_metrics_pages)
        render_device_metrics()
    elif gesture in [0x04, 0x0C]:  # LEFT or BACK
        current_menu = MENU_MAIN
        current_page = 0
        render_main_menu()

def handle_main_menu(gesture):
    """Handle main menu - don't clear gestures, already done in main loop"""
    global selected_option, current_menu, active_theme

    if gesture == 0x01:  # UP
        selected_option = (selected_option - 1) % len(items)
        render_main_menu()
    elif gesture == 0x02:  # DOWN
        selected_option = (selected_option + 1) % len(items)
        render_main_menu()
    elif gesture == 0x05:  # SELECT (tap)
        touch.get_point()
        x, y = touch.X_point, touch.Y_point

        # Coordinates for toggle emoji
        screen_width = 240
        emoji_y_range = (205, 235)
        emoji_w = get_font().getlength(TOGGLE_THEME_EMOJI)
        emoji_x_range = ((screen_width - emoji_w) // 2 - 10, (screen_width + emoji_w) // 2 + 10)

        if emoji_y_range[0] <= y <= emoji_y_range[1] and emoji_x_range[0] <= x <= emoji_x_range[1]:
            # Toggle theme
            active_theme = THEMES["light"] if active_theme.name == "dark" else THEMES["dark"]
            render_main_menu()
            time.sleep(0.2)
            return

        # Handle regular menu options
        time.sleep(0.1)  # Small delay before transition
        
        if selected_option == 0:
            current_menu = MENU_MQTT
            render_mqtt_data()
        elif selected_option == 1:
            current_menu = MENU_METRICS
            render_device_metrics()
        elif selected_option == 3:
            current_menu = MENU_CONFIRM_SHUTDOWN
            render_confirmation()
        elif selected_option == 2:
            current_menu = MENU_WIFI
            render_wifi_setup_menu()
        
        time.sleep(0.1)  # Prevent immediate trigger in new menu

def handle_touch():
    """Optimized touch handler with better debouncing and responsiveness"""
    global last_activity_time, is_standby, current_menu, current_page, selected_option
    global in_saved_networks_mode, last_gesture, last_gesture_time, last_render_time
    
    while True:
        current_time = time.time()
        gesture = touch.Gestures

        if is_standby:
            if gesture != 0:
                logging.info(f"Waking from standby. Gesture: {gesture}")
                is_standby = False
                last_activity_time = current_time
                touch.Stop_Sleep()
                touch.Set_Mode(0)
                lcd_wake()
                touch.Gestures = 0
                time.sleep(0.3)
                render_main_menu()
                last_gesture = None
                last_gesture_time = current_time
            time.sleep(0.08)
            continue

        # Continuously update for scrolling animations
        if gesture == 0:
            if in_saved_networks_mode:
                if current_time - last_render_time > RENDER_THROTTLE:
                    render_saved_networks()
                    last_render_time = current_time
            elif current_menu == MENU_CONFIRM_NETWORK:
                if current_time - last_render_time > RENDER_THROTTLE:
                    render_network_confirmation(network_to_connect)
                    last_render_time = current_time
        
        # Long press handling
        if gesture == 0x0C:
            touch.Gestures = 0
            logging.info("Long press detected. Returning to main menu.")
            time.sleep(0.2)
            current_menu = MENU_MAIN
            selected_option = 0
            current_page = 0
            in_saved_networks_mode = False
            render_main_menu()
            last_gesture = None
            last_gesture_time = current_time
            last_activity_time = current_time
            time.sleep(0.3)
            continue
        
        # Process other gestures
        if gesture != 0:
            is_new_gesture = (gesture != last_gesture) or (current_time - last_gesture_time > GESTURE_DEBOUNCE)
            
            if is_new_gesture:
                actual_gesture = gesture
                touch.Gestures = 0
                
                logging.info(f"Gesture detected: {actual_gesture}")
                last_gesture = actual_gesture
                last_gesture_time = current_time
                last_activity_time = current_time

                if current_menu == MENU_MAIN:
                    handle_main_menu(actual_gesture)
                elif current_menu == MENU_MQTT:
                    handle_mqtt_menu(actual_gesture)
                elif current_menu == MENU_METRICS:
                    handle_device_metrics_menu(actual_gesture)
                elif current_menu == MENU_WIFI:
                    handle_wifi_setup_menu(actual_gesture)
                elif current_menu == MENU_CONFIRM_SHUTDOWN:
                    handle_shutdown_menu(actual_gesture)
                elif current_menu == MENU_CONFIRM_NETWORK:
                    handle_network_confirmation(actual_gesture)
                
                touch.Gestures = 0
                time.sleep(0.15)
            else:
                touch.Gestures = 0

        # Standby check
        if not is_standby and (current_time - last_activity_time > STANDBY_TIMEOUT):
            logging.info("Inactivity detected. Entering standby mode.")
            is_standby = True
            lcd_sleep()
            touch.Configure_Standby(timeout=5)
            touch.Gestures = 0
            last_gesture = None

        time.sleep(0.04)
        
def start_page():
    image = logo.copy()
    draw = ImageDraw.Draw(image)
    draw.text((65, 80), 'Welcome', fill=get_text_color(), font=get_font())
    draw.text((110, 110), 'To', fill=get_text_color(), font=get_font())
    draw.text((90, 140), 'Orion', fill=get_text_color(), font=get_font())
    disp.ShowImage(image)
    time.sleep(5)

def cleanup_and_exit(signum, frame):
    logging.info("Exiting program...")
    disp.module_exit()
    sys.exit(0)

def optimize_display_performance(disp):
    """Optimize GC9A01A for maximum performance"""
    
    # Frame Rate Control (0xE8) - Increase refresh rate
    # Default is ~60Hz, we can push to ~117Hz for smoother scrolling
    disp.LCD_WriteReg(0x35)  # Tearing Effect Line ON
    disp.LCD_WriteData_Byte(0x00)  # V-blanking info only
    
    # Set RGB Interface Control (0xB0) for faster data transfer
    disp.LCD_WriteReg(0xB0)
    disp.LCD_WriteData_Byte(0x00)  # RGB interface off (we're using MCU interface)
    disp.LCD_WriteData_Byte(0xE0)  # 16-bit/pixel
    
    # Power Control (0xC3/0xC4) - Optimize power for performance
    disp.LCD_WriteReg(0xC3)
    disp.LCD_WriteData_Byte(0x13)  # VREG1A voltage
    
    disp.LCD_WriteReg(0xC4)
    disp.LCD_WriteData_Byte(0x13)  # VREG1B voltage
    
    # VCOM Control (0xC9) - Reduce ghosting/artifacts
    disp.LCD_WriteReg(0xC9)
    disp.LCD_WriteData_Byte(0x22)  # VCOM voltage

signal.signal(signal.SIGTERM, cleanup_and_exit)
signal.signal(signal.SIGINT, cleanup_and_exit)

if __name__ == "__main__":
    try: 
        disp = LCD_1inch28.LCD_1inch28()
        disp.Init()
        optimize_display_performance(disp) 
        disp.clear()
        touch = Touch_1inch28.Touch_1inch28()
        touch.init()
        touch.Configure_Standby(timeout=5)
        touch.int_irq(TP_INT, Int_Callback)
        
        device_metrics_pages = get_device_metrics()        
        threading.Thread(target=update_device_metrics_loop, daemon=True).start()
        
        mqtt_client = mqtt.Client(client_id="Orion_Publisher", protocol=mqtt.MQTTv311)
        mqtt_client.username_pw_set(username="orion_device", password="123456789")  # ✅ Add this line
        mqtt_client.connect(local_broker, port, 60)
        mqtt_client.loop_start()
        start_mqtt()
        start_page()
        render_main_menu()
        handle_touch()
    except IOError as e:
        logging.error(f"IOError: {e}")
        disp.module_exit()
    except KeyboardInterrupt:
        cleanup_and_exit(signal.SIGINT, None)

