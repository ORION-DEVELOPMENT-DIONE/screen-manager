#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
Orion Energy Monitor - Main Entry Point
"""
import sys
import os
import signal
import logging
import threading
import time
from PIL import Image, ImageDraw, ImageFont
from ui.wake_animation import play_boot_animation

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(parent_dir)

# Import hardware libraries
from lib import LCD_1inch28, Touch_1inch28

# Import application modules
from config.constants import *
from config.themes import THEMES
from utils.state import state
from utils.helpers import get_device_metrics, update_device_metrics_loop
from core.display import DisplayManager
from core.touch import TouchHandler
from core.mqtt import MQTTManager
from services.wifi_service import WiFiService
from services.data_logger import DataLogger
from ui.menus.main_menu import MainMenu
from ui.menus.wifi_menu import WiFiMenu
from ui.menus.energy_menu import EnergyMenu
from ui.menus.device_menu import DeviceMenu
from ui.menus.confirmation import ConfirmationMenu
from services.energy_analyzer import EnergyAnalyzer
from services.update_checker import UpdateChecker
from ui.menus.update_menu import UpdateMenu
from services.connectivity_service import ConnectivityService
from systemd.journal import JournalHandler

# Setup logging
log = logging.getLogger()
log.setLevel(logging.INFO)
jh = JournalHandler(SYSLOG_IDENTIFIER='screen-manager')
jh.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
log.addHandler(jh)
connectivity = ConnectivityService(state)
connectivity.start()

class MenuHandler:
    """Central menu handler"""
    def __init__(self, display, state, wifi_service, touch_device, energy_analyzer=None, update_checker=None):
        self.display = display
        self.state = state
        self.wifi_service = wifi_service
        self.touch_device = touch_device
        self.energy_analyzer = energy_analyzer
        self.update_checker = update_checker

        # Initialize menus
        self.main_menu = MainMenu(display, state)
        self.wifi_menu = WiFiMenu(display, state, wifi_service)
        self.energy_menu = EnergyMenu(display, state, energy_analyzer)
        self.device_menu = DeviceMenu(display, state)
        self.confirmation_menu = ConfirmationMenu(display, state)
        self.confirmation_menu.set_wifi_service(wifi_service)
        self.update_menu = UpdateMenu(display, state, update_checker)

    def render_current_menu(self):
        """Render current menu"""
        if self.state.current_menu == MENU_MAIN:
            self.main_menu.render()
        elif self.state.current_menu == MENU_WIFI:
            self.wifi_menu.render()
        elif self.state.current_menu == MENU_MQTT:
            self.energy_menu.render()
        elif self.state.current_menu == MENU_METRICS:
            self.device_menu.render()
        elif self.state.current_menu == MENU_CONFIRM_SHUTDOWN:
            self.confirmation_menu.render_shutdown_confirmation()
        elif self.state.current_menu == MENU_POWER_OPTIONS:
            self.confirmation_menu.render_power_options()
        elif self.state.current_menu == MENU_CONFIRM_RESTART:
            self.confirmation_menu.render_restart_confirmation()
        elif self.state.current_menu == MENU_CONFIRM_NETWORK:
            self.wifi_menu.render_network_confirmation()
        elif self.state.current_menu == MENU_CONFIRM_REMOVE_WIFI:
            self.confirmation_menu.render_remove_wifi_confirmation()
        elif self.state.current_menu == MENU_UPDATE:
            self.update_menu.render()

    def render_main_menu(self):
        """Render main menu"""
        self.state.current_menu = MENU_MAIN
        self.main_menu.render()
    
    def handle_gesture(self, gesture):
        """Route gesture to appropriate menu"""
        next_menu = None
        
        if self.state.current_menu == MENU_MAIN:
            next_menu = self.main_menu.handle_gesture(gesture, self.touch_device)
        elif self.state.current_menu == MENU_WIFI:
            next_menu = self.wifi_menu.handle_gesture(gesture, self.touch_device)
        elif self.state.current_menu == MENU_MQTT:
            next_menu = self.energy_menu.handle_gesture(gesture, self.touch_device)  
        elif self.state.current_menu == MENU_METRICS:
            next_menu = self.device_menu.handle_gesture(gesture, self.touch_device) 
        elif self.state.current_menu == MENU_CONFIRM_SHUTDOWN:
            next_menu = self.confirmation_menu.handle_shutdown_gesture(gesture, self.touch_device)
        elif self.state.current_menu == MENU_POWER_OPTIONS:
            next_menu = self.confirmation_menu.handle_power_options_gesture(gesture, self.touch_device)
        elif self.state.current_menu == MENU_CONFIRM_RESTART:
            next_menu = self.confirmation_menu.handle_restart_gesture(gesture, self.touch_device)
        elif self.state.current_menu == MENU_CONFIRM_NETWORK:
            next_menu = self.wifi_menu.handle_confirmation_gesture(gesture, self.touch_device)
        elif self.state.current_menu == MENU_CONFIRM_REMOVE_WIFI:
            next_menu = self.confirmation_menu.handle_remove_wifi_gesture(gesture, self.touch_device)       
        elif self.state.current_menu == MENU_UPDATE:
            next_menu = self.update_menu.handle_gesture(gesture, self.touch_device)

        if next_menu is not None:
            self.state.current_menu = next_menu
            time.sleep(0.1)
            self.render_current_menu()

def interrupt_callback(TP_INT=TP_INT):
    """Touch interrupt callback"""
    touch.Gestures = touch.Touch_Read_Byte(0x01)
    state.last_activity_time = time.time()

def show_startup_screen(display):
    play_boot_animation(display, quick=False)

def cleanup_and_exit(signum, frame):
    """Cleanup on exit"""
    logging.info("Exiting program...")
    try:
        if disp and hasattr(disp, 'disp'):
            disp.disp.module_exit()
    except Exception as e:
        logging.error(f"Cleanup error: {e}")
    finally:
        os._exit(0)  # Force exit without cleanup handlers

# Global hardware instances
disp = None
touch = None
menu_handler = None

if __name__ == "__main__":
    try:
        # Setup signal handlers
        signal.signal(signal.SIGTERM, cleanup_and_exit)
        signal.signal(signal.SIGINT, cleanup_and_exit)
        
        # Initialize hardware
        logging.info("Initializing hardware...")
        disp_hw = LCD_1inch28.LCD_1inch28()
        touch_hw = Touch_1inch28.Touch_1inch28()
        
        # Initialize display manager
        disp = DisplayManager(disp_hw)
        disp.init()
        
        # Initialize touch
        touch = touch_hw
        touch.init()
        touch.Configure_Standby(timeout=5)
        
        # Initialize services
        logging.info("Initializing services...")
        wifi_service = WiFiService()
        data_logger = DataLogger()
        energy_analyzer = EnergyAnalyzer() 
        update_checker = UpdateChecker(state, check_interval=3600)
        mqtt_manager = MQTTManager(state, data_logger, energy_analyzer)

        # Initialize menu handler
        menu_handler = MenuHandler(disp, state, wifi_service, touch, energy_analyzer, update_checker)
        
        # Initialize touch handler
        touch_handler = TouchHandler(touch, state, menu_handler)
        touch_handler.setup_callback(interrupt_callback)
        
        # Initialize device metrics
        state.device_metrics_pages = get_device_metrics()
        threading.Thread(target=update_device_metrics_loop, args=(state,), daemon=True).start()
        
        # Start MQTT
        logging.info("Starting MQTT...")
        mqtt_manager.init_client()
        
        # Show startup screen
        show_startup_screen(disp)
        
        # Render main menu
        menu_handler.render_main_menu()
        
        # Start touch handling loop
        logging.info("Starting main loop...")
        touch_handler.handle_loop()
        
    except IOError as e:
        logging.error(f"IOError: {e}")
        if disp:
            disp.disp.module_exit()
    except KeyboardInterrupt:
        cleanup_and_exit(signal.SIGINT, None)
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        if disp:
            disp.disp.module_exit()
