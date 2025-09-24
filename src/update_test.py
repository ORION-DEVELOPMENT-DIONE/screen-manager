143#! /usr/bin/python
# -*- coding: UTF-8 -*-
import paho.mqtt.client as mqtt
import signal
import json
import threading
import os
import sys 
import subprocess
import urllib.request
print(sys.path)
import time
import logging
import spidev as SPI
import qrcode
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(parent_dir)
import psutil  # For getting device metrics like CPU usage
from datetime import datetime
from lib import LCD_1inch28, Touch_1inch28
from PIL import Image, ImageDraw, ImageFont

# Setup logging
logging.basicConfig(filename='../logs/orion-update.log', level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s') 

# --- Theme and UI Style Definitions ---
class Theme:
    def __init__(self, name, background_path, font_path, font_size, text_color, selected_color):
        self.name = name
        self.background_path = background_path
        self.font = ImageFont.truetype(font_path, font_size)
        self.text_color = text_color
        self.selected_color = selected_color

THEMES = {
    "light": Theme("light", "../pic/bg_light.jpg", "../Font/DejaVuSans.ttf", 24, "black", "blue"),
    "dark": Theme("dark", "../pic/bg_dark.jpg", "../Font/DejaVuSans.ttf", 24, "white", "cyan"),
}

active_theme = THEMES["dark"]
logo = Image.open("../pic/dione-logo.jpg").convert("RGB")
emoji_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
TOGGLE_THEME_EMOJI = "🌗"
BELL_EMOJI = "🔔"

# Constants
RST, DC, BL, TP_INT = 6, 25, 22, 9
MENU_MAIN, MENU_MQTT, MENU_METRICS, MENU_WIFI, MENU_CONFIRM_SHUTDOWN, MENU_UPDATE = 0, 1, 3, 2, 4, 5
STANDBY_TIMEOUT = 60

# MQTT Settings
local_broker = "localhost"
public_broker = "test.mosquitto.org"
port = 1883
topic_energy = "energy/metrics"
log_file = "mqtt_data_log.txt"
mqtt_client = None

# Update system config (customize these)
UPDATE_CHECK_URL = "https://your-update-server.example.com/orion-update.json"  # expected JSON {"update": true, "count":1}
UPDATE_CHECK_INTERVAL = 60 * 5  # 5 minutes
ANSIBLE_PULL_REPOS = [
    "https://github.com/AmirHassenBenHassine/wifi-manager.git",
    "https://github.com/youruser/orion-screen.git",
]
ANSIBLE_BRANCH = "main"
UPDATE_LOG_FILE = "update_log.txt"

# Global Variables
items = ["Energy", "Device", "WiFi Setup", "Shutdown", "Update"]
current_menu = MENU_MAIN
selected_option = 0  # absolute index in items
menu_offset = 0
VISIBLE_MENU_ITEMS = 5  # number of menu entries shown at once
current_page = 0
energy_metrics = []
wifi_options = ["Configure WiFi", "Reset WiFi"]
wifi_selected = 0
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

# Update state
update_available = False
update_count = 0
update_in_progress = False
update_log_lock = threading.Lock()
auto_check_enabled = True  # run periodic status checks
manual_check_in_progress = False

# Helper UI utilities
def get_background_copy():
    return Image.open(active_theme.background_path).convert("RGB")

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

# Drawing charts (unchanged)
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
    draw.text((60, 10), "Power(W)", fill=get_text_color(), font=get_font())
    bar_colors = ["red", "green", "blue"]
    for i, phase in enumerate(phases):
        power = phase.get("power", 0)
        bar_height = int((power / max_power) * max_bar_height)
        x = start_x + i * (bar_width + spacing)
        y = origin_y - bar_height
        draw.rectangle([x, y, x + bar_width, origin_y], fill=bar_colors[i % len(bar_colors)])
        value_text = f"{int(power)}"
        value_w = get_font().getlength(value_text)
        draw.text((x + (bar_width - value_w) // 2, y - 18), value_text, fill=get_text_color(), font=get_font())
        label = f"P{i+1}"
        label_w = get_font().getlength(label)
        draw.text((x + (bar_width - label_w) // 2, origin_y + 5), label, fill=get_text_color(), font=get_font())
    disp.ShowImage(image)

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
    title = "Current per Phase"
    draw.text((60, 10), title, fill=get_text_color(), font=get_font())
    draw.line([(chart_left, chart_top), (chart_left, chart_bottom)], fill="gray")
    draw.line([(chart_left, chart_bottom), (chart_left + chart_width, chart_bottom)], fill="gray")
    colors = ["red", "green", "blue"]
    for i in range(1, len(values)):
        x1 = chart_left + (i - 1) * (chart_width // (len(values) - 1))
        y1 = chart_bottom - int((values[i - 1] - min_val) * scale)
        x2 = chart_left + i * (chart_width // (len(values) - 1))
        y2 = chart_bottom - int((values[i] - min_val) * scale)
        draw.line([x1, y1, x2, y2], fill=colors[i % len(colors)], width=2)
    disp.ShowImage(image)

# Touch interrupt callback
def Int_Callback(TP_INT=TP_INT):
    global Mode, Flag, last_activity_time
    if Mode == 1:
        Flag = 1
        touch.get_point()
    else:
        touch.Gestures = touch.Touch_Read_Byte(0x01)
    last_activity_time = time.time()

# MQTT handlers
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info(f"Connected to MQTT broker with code {rc}")
        client.subscribe(topic_energy)
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
            energy_metrics.append(f"Voltage: {data.get('voltage', 'N/A')} V")
            tp = data.get("totalPower", None)
            energy_metrics.append(f"Total Power: {tp:.2f} W" if isinstance(tp, (int, float)) else f"Total Power: {tp}")
            energy_metrics.append(f"Energy Total: {data.get('energyTotal', 'N/A')} kWh")
            energy_metrics.append(f"Runtime: {data.get('runTime', 0)} sec")
            phases = data.get("phases", [])
            for idx, phase in enumerate(phases):
                current = phase.get("current", 0.0)
                power = phase.get("power", 0.0)
                energy_metrics.append(f"Phase {idx+1}: {power:.2f}W / {current:.2f}A")
            render_page(current_page)
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
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(broker, port, 60)
        client.loop_forever()
    except Exception as e:
        logging.error(f"{client_name} connection failed: {e}")

def start_mqtt():
    threading.Thread(target=start_mqtt_client, args=(local_broker, "Local_Client"), daemon=True).start()
    threading.Thread(target=start_mqtt_client, args=(public_broker, "Public_Client"), daemon=True).start()

# Rendering helpers and menus
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
        screen_width, screen_height = image.size
        arrow_x = screen_width // 2 - 10
        draw.text((arrow_x, 10), "▲", fill=get_selected_color(), font=get_font())
        draw.text((arrow_x, screen_height - 30), "▼", fill=get_selected_color(), font=get_font())
        disp.ShowImage(image)
    elif chart_mode == 1:
        draw_power_chart(energy_data.get("phases", []))
    elif chart_mode == 2:
        currents = [p.get("current", 0) for p in energy_data.get("phases", [])]
        draw_line_chart(currents)

def render_main_menu():
    global menu_offset
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size
    # Show a slice of items depending on menu_offset
    visible = items[menu_offset:menu_offset + VISIBLE_MENU_ITEMS]
    height = len(visible) * 40
    y_start = (screen_height - height) // 2
    for i, option in enumerate(visible):
        absolute_index = menu_offset + i
        prefix = "➤ " if absolute_index == selected_option else "  "
        # Add update flag if this is the Update entry and update is available
        label = option
        if option == "Update" and update_available:
            label = f"({update_count}) {label}"
        color = get_selected_color() if absolute_index == selected_option else get_text_color()
        # If update entry and not selected, highlight color to indicate notification
        if option == "Update" and update_available and absolute_index != selected_option:
            color = get_selected_color()
        w = get_font().getlength(prefix + label)
        draw.text(((screen_width - w) // 2, y_start + i * 40), prefix + label, fill=color, font=get_font())
    # bell icon top-right if update available
    if update_available:
        draw.text((screen_width - 40, 5), BELL_EMOJI, fill=get_selected_color(), font=emoji_font)
    emoji_w = get_font().getlength(TOGGLE_THEME_EMOJI)
    draw.text(((screen_width - emoji_w) // 2, screen_height - 35), TOGGLE_THEME_EMOJI, fill=get_selected_color(), font=get_font())
    disp.ShowImage(image)

def render_confirmation():
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size
    msg = "Shutdown?"
    w = get_font().getlength(msg)
    draw.text(((screen_width - w) // 2, 50), msg, fill=get_text_color(), font=get_font())
    box_w, box_h = 90, 50
    box_y = 120
    spacing = 20
    total_width = 2 * box_w + spacing
    start_x = (screen_width - total_width) // 2
    draw.rectangle([start_x, box_y, start_x + box_w, box_y + box_h], outline=get_selected_color(), width=2)
    no_text = "No"
    no_w = get_font().getlength(no_text)
    draw.text((start_x + (box_w - no_w) // 2, box_y + 10), no_text, fill=get_selected_color(), font=get_font())
    draw.rectangle([start_x + box_w + spacing, box_y, start_x + 2 * box_w + spacing, box_y + box_h], outline=get_text_color(), width=2)
    yes_text = "Yes"
    yes_w = get_font().getlength(yes_text)
    draw.text((start_x + box_w + spacing + (box_w - yes_w) // 2, box_y + 10), yes_text, fill=get_text_color(), font=get_font())
    disp.ShowImage(image)

def render_wifi_qr_code():
    url = "http://orion.local:3000"
    qr = qrcode.make(url)
    image = Image.new("RGB", (240, 240), "BLACK")
    image.paste(qr.resize((200, 200)), (20, 20))
    disp.ShowImage(image)
    logging.info("Displayed Wi-Fi setup QR code.")

def render_wifi_setup_menu():
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size
    height = len(wifi_options) * 40
    y_start = (screen_height - height) // 2
    for i, item in enumerate(wifi_options):
        prefix = "➤ " if i == wifi_selected else "  "
        text = prefix + item
        color = get_selected_color() if i == wifi_selected else get_text_color()
        w = get_font().getlength(text)
        draw.text(((screen_width - w) // 2, y_start + i * 40), text, fill=color, font=get_font())
    disp.ShowImage(image)

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

def render_update_menu(selected_index=0):
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    screen_width, screen_height = image.size
    options = ["Check for updates", "Run update now", "Update log", "Back"]
    height = len(options) * 40
    y_start = (screen_height - height) // 2
    # Header with status
    status_text = "Update: Available" if update_available else "Update: Up to date"
    draw.text((20, 10), status_text, fill=get_text_color(), font=get_font())
    for i, opt in enumerate(options):
        prefix = "➤ " if i == selected_index else "  "
        color = get_selected_color() if i == selected_index else get_text_color()
        draw.text((20, y_start + i * 40), prefix + opt, fill=color, font=get_font())
    disp.ShowImage(image)

def render_message(message):
    image = get_background_copy()
    draw = ImageDraw.Draw(image)
    lines = wrap_text(message, get_font(), max_width=220)
    y = 80
    for line in lines:
        draw.text((20, y), line, fill=get_text_color(), font=get_font())
        y += 30
    disp.ShowImage(image)
    logging.info(f"Rendered message: {message}")

def lcd_sleep():
    logging.info("Putting display to sleep.")
    disp.LCD_WriteReg(0x28)
    disp.LCD_WriteReg(0x10)

def lcd_wake():
    logging.info("Waking display from sleep.")
    disp.LCD_WriteReg(0x11)
    time.sleep(0.12)
    disp.LCD_WriteReg(0x29)

# Shutdown handler
def handle_shutdown_menu(gesture):
    global current_menu
    if gesture == 0x0C:
        current_menu = MENU_MAIN
        render_main_menu()
    elif gesture == 0x05:
        touch.get_point()
        x, y = touch.X_point, touch.Y_point
        box_w, box_h = 90, 50
        box_y = 120
        spacing = 20
        start_x = (240 - (2 * box_w + spacing)) // 2
        if start_x <= x <= start_x + box_w and box_y <= y <= box_y + box_h:
            current_menu = MENU_MAIN
            render_main_menu()
        elif start_x + box_w + spacing <= x <= start_x + 2 * box_w + spacing and box_y <= y <= box_y + box_h:
            render_message("Shutting down...")
            time.sleep(2)
            os.system("sudo shutdown now")

# Device metrics
def update_device_metrics_loop():
    global device_metrics_pages
    while True:
        if not is_standby:
            device_metrics_pages = get_device_metrics()
        time.sleep(5)

def get_device_metrics():
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory().percent
    uptime = int(time.time() - psutil.boot_time())
    uptime_str = time.strftime('%H:%M:%S', time.gmtime(uptime))

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

# Update system functions
def append_update_log(line):
    with update_log_lock:
        with open(UPDATE_LOG_FILE, "a") as f:
            f.write(f"{datetime.now().isoformat()} {line}\n")

def run_ansible_pull(repo_url):
    """Run ansible-pull for a single repo. Returns True on success."""
    cmd = ["ansible-pull", "-U", repo_url, "-C", ANSIBLE_BRANCH]
    append_update_log(f"Starting ansible-pull {repo_url}")
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for l in p.stdout:
            append_update_log(l.rstrip())
        ret = p.wait()
        append_update_log(f"ansible-pull exit {ret} for {repo_url}")
        return ret == 0
    except Exception as e:
        append_update_log(f"ansible-pull exception: {e}")
        return False

def run_update_now():
    global update_in_progress, update_available, update_count
    if update_in_progress:
        return
    update_in_progress = True
    append_update_log("Manual update triggered.")
    render_message("⚡ Running update...")

    success_all = True
    for repo in ANSIBLE_PULL_REPOS:
        ok = run_ansible_pull(repo)
        success_all = success_all and ok

    if success_all:
        append_update_log("✅ Update completed successfully.")
        render_message("✅ Update complete")
        update_available = False
        update_count = 0
    else:
        append_update_log("❌ One or more updates failed.")
        render_message("❌ Update failed")
    update_in_progress = False

def trigger_manual_check():
    """Immediate check of UPDATE_CHECK_URL for status."""
    global update_available, update_count
    try:
        with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if data.get("update"):
                update_available = True
                update_count = int(data.get("count", 1))
                append_update_log(f"Server indicates update available: count={update_count}")
            else:
                update_available = False
                update_count = 0
                append_update_log("Server indicates no update.")
    except Exception as e:
        append_update_log(f"Manual check failed: {e}")

def update_checker_loop():
    """Periodically check server for update flag. If auto_check_enabled and ansible-pull scheduled, could run automatically."""
    while True:
        if auto_check_enabled:
            try:
                with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get("update"):
                        global update_available, update_count
                        update_available = True
                        update_count = int(data.get("count", 1))
                        append_update_log(f"Periodic check: update available count={update_count}")
                    else:
                        update_available = False
                        update_count = 0
                        append_update_log("Periodic check: no update")
            except Exception as e:
                append_update_log(f"Periodic check failed: {e}")
        time.sleep(UPDATE_CHECK_INTERVAL)

# Update menu handling
def handle_update_menu(gesture):
    """Simple menu with index navigation for update actions."""
    selected = 0
    render_update_menu(selected)
    while True:
        g = touch.Gestures
        if g != 0:
            if g == 0x01:  # UP
                selected = (selected - 1) % 4
                render_update_menu(selected)
            elif g == 0x02:  # DOWN
                selected = (selected + 1) % 4
                render_update_menu(selected)
            elif g == 0x05:  # SELECT
                if selected == 0:
                    render_message("Checking for updates...")
                    trigger_manual_check()
                    time.sleep(1)
                    render_update_menu(selected)
                elif selected == 1:
                    if update_in_progress:
                        render_message("Update already in progress")
                    else:
                        render_message("Running update...")
                        threading.Thread(target=run_update_now, daemon=True).start()
                    time.sleep(1)
                    render_update_menu(selected)
                elif selected == 2:
                    # Show last lines of update log
                    try:
                        with open(UPDATE_LOG_FILE, "r") as f:
                            lines = f.read().splitlines()[-8:]
                            render_message("\n".join(lines) if lines else "No logs")
                    except FileNotFoundError:
                        render_message("No logs")
                    time.sleep(2)
                    render_update_menu(selected)
                elif selected == 3:
                    render_main_menu()
                    return
            elif g in [0x04, 0x0C]:  # BACK
                render_main_menu()
                return
            touch.Gestures = 0
        time.sleep(0.08)

# Menu handlers
def handle_mqtt_menu(gesture):
    global current_page, current_menu, energy_metrics, show_energy_chart, chart_mode
    if not energy_metrics:
        logging.info("No MQTT data available. Only BACK gesture allowed.")
        if gesture in [0x04, 0x0C]:
            current_menu = MENU_MAIN
            render_main_menu()
        return
    if gesture == 0x01:
        current_page = (current_page - 1) % len(energy_metrics)
        render_page(current_page)
    elif gesture == 0x02:
        current_page = (current_page + 1) % len(energy_metrics)
        render_page(current_page)
    elif gesture == 0x05:
        chart_mode = (chart_mode + 1) % 3
        render_page(current_page)
    elif gesture in [0x04, 0x0C]:
        current_menu = MENU_MAIN
        show_energy_chart = False
        render_main_menu()

def handle_device_metrics_menu(gesture):
    global current_page, current_menu, device_metrics_pages
    if not device_metrics_pages:
        device_metrics_pages = get_device_metrics()
    if gesture == 0x01:
        current_page = (current_page - 1) % len(device_metrics_pages)
        render_device_metrics()
    elif gesture == 0x02:
        current_page = (current_page + 1) % len(device_metrics_pages)
        render_device_metrics()
    elif gesture in [0x04, 0x0C]:
        current_menu = MENU_MAIN
        current_page = 0
        render_main_menu()

def handle_wifi_setup_menu(gesture):
    global wifi_selected, current_menu, in_wifi_qr_mode
    if in_wifi_qr_mode:
        if gesture == 0x04:
            in_wifi_qr_mode = False
            current_menu = MENU_WIFI
            render_wifi_setup_menu()
        elif gesture == 0x0C:
            in_wifi_qr_mode = False
            current_menu = MENU_MAIN
            render_main_menu()
        return
    if gesture == 0x01:
        wifi_selected = (wifi_selected - 1) % len(wifi_options)
        render_wifi_setup_menu()
    elif gesture == 0x02:
        wifi_selected = (wifi_selected + 1) % len(wifi_options)
        render_wifi_setup_menu()
    elif gesture == 0x05:
        if wifi_selected == 0:
            render_message("Configuring WiFi...")
            mqtt_client.publish("orion/trigger", json.dumps({"action": "reset"}), retain=True)
            time.sleep(1)
            render_wifi_qr_code()
            in_wifi_qr_mode = True
        elif wifi_selected == 1:
            render_message("Resetting WiFi...")
            mqtt_client.publish("orion/trigger", json.dumps({"action": "reset"}), retain=True)
            time.sleep(1)
            render_wifi_qr_code()
            in_wifi_qr_mode = True
    elif gesture in [0x04, 0x0C]:
        current_menu = MENU_MAIN
        render_main_menu()

def handle_main_menu(gesture):
    global selected_option, current_menu, active_theme, menu_offset
    # UP / DOWN move selected; adjust menu_offset to keep selected visible
    if gesture == 0x01:
        selected_option = (selected_option - 1) % len(items)
        if selected_option < menu_offset:
            menu_offset = selected_option
        render_main_menu()
    elif gesture == 0x02:
        selected_option = (selected_option + 1) % len(items)
        if selected_option >= menu_offset + VISIBLE_MENU_ITEMS:
            menu_offset = selected_option - VISIBLE_MENU_ITEMS + 1
        render_main_menu()
    elif gesture == 0x05:  # SELECT (tap)
        touch.get_point()
        x, y = touch.X_point, touch.Y_point
        screen_width = 240
        emoji_y_range = (205, 235)
        emoji_w = get_font().getlength(TOGGLE_THEME_EMOJI)
        emoji_x_range = ((screen_width - emoji_w) // 2 - 10, (screen_width + emoji_w) // 2 + 10)
        if emoji_y_range[0] <= y <= emoji_y_range[1] and emoji_x_range[0] <= x <= emoji_x_range[1]:
            active_theme = THEMES["light"] if active_theme.name == "dark" else THEMES["dark"]
            render_main_menu()
            return
        sel = selected_option
        if sel == 0:
            current_menu = MENU_MQTT
            render_mqtt_data()
        elif sel == 1:
            current_menu = MENU_METRICS
            render_device_metrics()
        elif sel == 3:
            current_menu = MENU_CONFIRM_SHUTDOWN
            render_confirmation()
        elif sel == 2:
            current_menu = MENU_WIFI
            render_wifi_setup_menu()
        elif items[sel] == "Update":
            current_menu = MENU_UPDATE
            render_update_menu(0)
            # enter update sub-loop
            handle_update_menu(0)
    elif gesture in [0x04, 0x0C]:
        # back / long press -> do nothing on main
        render_main_menu()

# Touch loop
def handle_touch():
    global last_activity_time, is_standby, current_menu, current_page, selected_option
    last_gesture = None
    last_gesture_time = 0
    while True:
        gesture = touch.Gestures
        if is_standby:
            if gesture != 0:
                logging.info(f"Waking from standby. Gesture: {gesture}")
                is_standby = False
                last_activity_time = time.time()
                touch.Stop_Sleep()
                touch.Set_Mode(0)
                lcd_wake()
                render_main_menu()
                touch.Gestures = 0
            time.sleep(0.08)
            continue
        now = time.time()
        if gesture == 0x0C:
            logging.info("Long press detected. Returning to main menu.")
            current_menu = MENU_MAIN
            selected_option = 0
            current_page = 0
            render_main_menu()
            touch.Gestures = 0
            continue
        elif gesture != 0 and (gesture != last_gesture or now - last_gesture_time > 0.4):
            logging.info(f"Gesture detected: {gesture}")
            last_gesture = gesture
            last_gesture_time = now
            last_activity_time = now
            if current_menu == MENU_MAIN:
                handle_main_menu(gesture)
            elif current_menu == MENU_MQTT:
                handle_mqtt_menu(gesture)
            elif current_menu == MENU_METRICS:
                handle_device_metrics_menu(gesture)
            elif current_menu == MENU_WIFI:
                handle_wifi_setup_menu(gesture)
            elif current_menu == MENU_CONFIRM_SHUTDOWN:
                handle_shutdown_menu(gesture)
            elif current_menu == MENU_UPDATE:
                # Update menu has its own internal loop; ignore here
                pass
            touch.Gestures = 0
        if not is_standby and (now - last_activity_time > STANDBY_TIMEOUT):
            logging.info("Inactivity detected. Entering standby mode.")
            is_standby = True
            lcd_sleep()
            touch.Configure_Standby(timeout=5)
            touch.Gestures = 0
        time.sleep(0.08)

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
    try:
        disp.module_exit()
    except:
        pass
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup_and_exit)
signal.signal(signal.SIGINT, cleanup_and_exit)

if __name__ == "__main__":
    try:
        disp = LCD_1inch28.LCD_1inch28()
        disp.Init()
        disp.clear()
        touch = Touch_1inch28.Touch_1inch28()
        touch.init()
        touch.Configure_Standby(timeout=5)
        touch.int_irq(TP_INT, Int_Callback)
        device_metrics_pages = get_device_metrics()
        threading.Thread(target=update_device_metrics_loop, daemon=True).start()
        # start update checker thread
        threading.Thread(target=update_checker_loop, daemon=True).start()
        mqtt_client = mqtt.Client(client_id="Orion_Publisher", protocol=mqtt.MQTTv311)
        mqtt_client.connect(local_broker, port, 60)
        mqtt_client.loop_start()
        start_mqtt()
        start_page()
        render_main_menu()
        handle_touch()
    except IOError as e:
        logging.error(f"IOError: {e}")
        try:
            disp.module_exit()
        except:
            pass
    except KeyboardInterrupt:
        cleanup_and_exit(signal.SIGINT, None)
