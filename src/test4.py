#!/usr/bin/python
# -*- coding: UTF-8 -*-
import paho.mqtt.client as mqtt
import signal
import json
import threading
import os
import sys 
import time
import logging
import spidev as SPI
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(parent_dir)
#sys.path.append("..")
import psutil  # For getting device metrics like CPU usage
from datetime import datetime
from lib import LCD_1inch28, Touch_1inch28
from PIL import Image, ImageDraw, ImageFont

RST = 6
DC = 25
BL = 22
TP_INT = 9

Mode = 0

# MQTT settings
local_broker = "localhost"
public_broker = "test.mosquitto.org"
port = 1883
topic_energy = "energy/metrics"

# Log file for saving received MQTT data
log_file = "mqtt_data_log.txt"

# Constants for Menu Options
#WELCOME_PAGE = 0
MENU_MAIN = 0
MENU_MQTT = 1
MENU_METRICS = 2

# Global variables
current_menu = MENU_MAIN
selected_option = 0
current_page = 0
pages = []  # Example pages, replace with actual MQTT data
device_metrics_pages = []
energy_metrics = []
last_mqtt_data = None  # This will hold the last MQTT message

def Int_Callback(TP_INT = TP_INT):       
    if Mode == 1:
        global Flag 
        Flag = 1
        touch.get_point()
    else:
        touch.Gestures = touch.Touch_Read_Byte(0x01)

# MQTT callback functions
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"Connected to MQTT Broker with code {rc}")
        client.subscribe(topic_energy)
    else:
        print(f"Failed to connect, return code {rc}")
        logging.error(f"MQTT Connection failed with code {rc}")


def on_message(client, userdata, msg):
    global current_page, energy_metrics

    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        # Log the received data to a file
        log_received_data(data)

        # Clear existing pages
        energy_metrics.clear()

        # Generate pages dynamically based on JSON keys and values
        for key, value in data.items():
            page_content = f"{key}: {value}"  # Create a page for each key-value pair
            energy_metrics.append(page_content)

        # After processing the data, render the current page
        render_page(current_page)
        print(f"Updated Data: {data}")
    
    except Exception as e:
        logging.error(f"Failed to process message: {e}")

def log_received_data(data):
    """Log received MQTT data to a file with a timestamp."""
    try:
        with open(log_file, "a") as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"{timestamp} - Received Data: {json.dumps(data)}\n"
            f.write(log_entry)
            #print(f"Logged data: {log_entry.strip()}")
    except Exception as e:
        logging.error(f"Error logging data: {e}")

# MQTT setup
def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    connected = False

    try:
        logging.info("Attempting to connect to local broker...")
        client.connect(local_broker, port, 60)
        connected = True
    except Exception as e:
        logging.warning(f"Local broker connection failed: {e}")
        try:
            logging.info("Attempting to connect to public broker...")
            client.connect(public_broker, port, 60)
            connected = True
        except Exception as e:
            logging.error(f"Public broker connection failed: {e}")

    if connected:
        try:
            logging.info("Waiting for MQTT data..")
            client.loop_forever()

        except KeyboardInterrupt:
            logging.info("Disconnected from MQTT Broker")
    else:
        logging.error("Failed to connect to any MQTT broker. Exiting.")

def render_page(index):
    """Render a specific page."""
    global energy_metrics
    if not energy_metrics:
        logging.warning("No pages to display.")
        return
    if index < 0 or index >= len(energy_metrics):
        logging.warning(f"Invalid page index: {index}")
        return
    logging.info(f"Rendering page: {energy_metrics[index]}")
    image = Image.open("../pic/bg5.jpg", mode="r", formats=None).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("../Font/Font00.ttf", 24)
    draw.text((20, 80), energy_metrics[index], fill="WHITE", font=font)
    disp.ShowImage(image)

def render_main_menu():
    """Render the main menu."""
    menu_items = ["Energy", "Device"]
    image = Image.open("../pic/bg4.jpg", mode="r", formats=None).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("../Font/Font00.ttf", 24)

    # Calculate the total height of the menu (sum of item heights + padding)
    total_menu_height = len(menu_items) * 40  # 40px per item (can be adjusted)
    
    # Get the height and width of the screen or image
    screen_width, screen_height = image.size

    # Calculate the vertical starting position (center vertically)
    start_y = (screen_height - total_menu_height) // 2

    # Loop through each menu item and calculate the horizontal position for centering
    for i, item in enumerate(menu_items):
        text_width, text_height = draw.textsize(item, font=font)
        start_x = (screen_width - text_width) // 2  # Center the text horizontally
        color = "WHITE" if i == selected_option else "GRAY"
        draw.text((start_x, start_y + i * 40), item, fill=color, font=font)
        time.sleep(0.1)

    disp.ShowImage(image)


def handle_main_menu(gesture):
    """Handle gestures in the main menu."""
    global selected_option, current_menu
    if gesture == 0x01:  # UP
        selected_option = (selected_option - 1) % 2
        render_main_menu()
    elif gesture == 0x02:  # DOWN
        selected_option = (selected_option + 1) % 2
        render_main_menu()
    elif gesture == 0x05:  # SELECT (e.g., Single Click)
        if selected_option == 0:
            current_menu = MENU_MQTT
            render_mqtt_data()
        elif selected_option == 1:
            current_menu = MENU_METRICS
            render_device_metrics()
    elif gesture == 0x0C:  # Long press
        current_menu = MENU_MAIN  # Go back to main menu
        selected_option = 0  # Reset to the first option
        render_main_menu()  # Re-render the main menu to refresh the screen
        touch.last_gesture = None  # Reset gesture state to avoid stale gestures


def get_device_metrics():
    """Get device metrics as a list of strings for pagination."""
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    uptime = time.time() - psutil.boot_time()
    return [
        f"CPU Usage: {cpu}%",
        f"Memory Usage: {mem}%",
        f"Uptime: {time.strftime('%H:%M:%S', time.gmtime(uptime))}"
    ]

def render_mqtt_data():
    """Render MQTT data on the screen."""
    global current_page, energy_metrics, last_mqtt_data
    
    if not energy_metrics:
        # No MQTT data available, display "No MQTT Data"
        render_message("No MQTT Data")
    else:
        # Display the current MQTT data for the selected page
        current_data = energy_metrics[current_page]
        render_page(current_page)
    
    # Display the last received MQTT data (if available) when no data is available
    if not energy_metrics and last_mqtt_data:
        render_message(f"Last MQTT Data: {last_mqtt_data}")

def handle_mqtt_menu(gesture):
    """Handle gestures in the MQTT menu."""
    global current_page, current_menu, energy_metrics, last_mqtt_data
    if len(energy_metrics) == 0:
        # No MQTT data, allow BACK gesture (0x0C) to go to the main menu
        if gesture == 0x0C:  # BACK
            current_menu = MENU_MAIN
            render_main_menu()
        else:
            # Only show message and do not navigate
            print("No MQTT data available. Please wait for data.")
        return  # Exit to avoid other gesture handling

    if gesture == 0x03:  # LEFT
        current_page = (current_page - 1) % len(energy_metrics)
        render_mqtt_data()
    elif gesture == 0x04:  # RIGHT
        current_page = (current_page + 1) % len(energy_metrics)
        render_mqtt_data()
    elif gesture == 0x0C:  # BACK
        current_menu = MENU_MAIN
        render_main_menu()

def on_new_mqtt_data(data):
    """Callback for new MQTT data."""
    global energy_metrics, last_mqtt_data
    
    # Update the last MQTT data and energy metrics
    last_mqtt_data = data
    energy_metrics.append(data)
    
    # Refresh the display if in MQTT menu
    if current_menu == MENU_MQTT:
        render_mqtt_data()


def render_device_metrics():
    """Render the current device metrics page."""
    global current_page, device_metrics_pages
    if not device_metrics_pages:
        device_metrics_pages = get_device_metrics()  # Populate the pages

    if current_page < 0 or current_page >= len(device_metrics_pages):
        current_page = 0  # Reset to the first page if out of bounds

    image = Image.open("../pic/bg5.jpg", mode="r", formats=None).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("../Font/Font00.ttf", 24)
    draw.text((20, 80), device_metrics_pages[current_page], fill="WHITE", font=font)
    disp.ShowImage(image)


def handle_device_metrics_menu(gesture):
    """Handle gestures in the Device Metrics menu."""
    global current_page, current_menu, device_metrics_pages
    if not device_metrics_pages:
        device_metrics_pages = get_device_metrics()  # Populate the pages

    if gesture == 0x03:  # LEFT
        current_page = (current_page - 1) % len(device_metrics_pages)
        render_device_metrics()
    elif gesture == 0x04:  # RIGHT
        current_page = (current_page + 1) % len(device_metrics_pages)
        render_device_metrics()
    elif gesture == 0x0C:  # BACK
        current_menu = MENU_MAIN
        current_page = 0  # Reset to the first page
        render_main_menu()


def render_message(message):
    """Display a simple message."""
    image = Image.open("../pic/bg5.jpg", mode="r", formats=None).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("../Font/Font00.ttf", 24)
    draw.text((20, 80), message, fill="WHITE", font=font)
    disp.ShowImage(image)

# Main Gesture Handling Loop
def handle_touch():
    last_gesture = None  # Track the last gesture to avoid redundant actions
    while True:
        gesture = touch.Gestures
        
        # Avoid multiple detections of the same gesture
        if gesture != last_gesture:
            last_gesture = gesture  # Update the last gesture   
            #if current_menu == WELCOME_PAGE:
                #start_page()
            if current_menu == MENU_MAIN:
                handle_main_menu(gesture)
            elif current_menu == MENU_MQTT:
                handle_mqtt_menu(gesture)
            elif current_menu == MENU_METRICS:
                handle_device_metrics_menu(gesture)
            
            time.sleep(0.1)


def start_page():
    try:
        image = Image.open("../pic/dione-logo.jpg", mode="r", formats=None).convert("RGB")
        welcome = ImageDraw.Draw(image)
        font = ImageFont.truetype("../Font/Font00.ttf", 24)
        
        timeout = time.time() + 5  # Timeout after 10 seconds
        while time.time() < timeout: #touch.Gestures != 0x05 and
            welcome.text((65, 80), 'Welcome', fill="WHITE", font=font)
            welcome.text((110, 110), 'To', fill="WHITE", font=font)
            welcome.text((90, 140), 'Orion', fill="WHITE", font=font)
            disp.ShowImage(image)
            time.sleep(0.5)  # Prevent excessive rendering
        time.sleep(0.01)
        
    except Exception as e:
        logging.error(f"Error in start_page: {e}")


def cleanup_and_exit(signum, frame):
    logging.info("Termination signal received. Cleaning up and exiting...")
    disp.module_exit()  # Ensure the screen shuts down properly
    sys.exit(0)

# Register the signal handler for SIGTERM and SIGINT (Ctrl+C)
signal.signal(signal.SIGTERM, cleanup_and_exit)
signal.signal(signal.SIGINT, cleanup_and_exit)

# Main Execution
try:
    # Initialize Display and Touch
    disp = LCD_1inch28.LCD_1inch28()
    disp.Init()
    disp.clear()
    touch = Touch_1inch28.Touch_1inch28()
    touch.init()
    touch.int_irq(TP_INT, Int_Callback)    

    # Start MQTT in a separate thread
    mqtt_thread = threading.Thread(target=start_mqtt)
    mqtt_thread.daemon = True
    mqtt_thread.start()

    start_page()       # Show the welcome page
    render_main_menu() # Transition to the main menu
    handle_touch()     # Start handling touch gestures
except IOError as e:
    logging.error(e)
    disp.module_exit()    
except KeyboardInterrupt:
    #disp.module_exit()
    cleanup_and_exit(signal.SIGINT, None)
    logging.info("Program terminated.")
    exit()

