"""Touch handling"""
import time
import logging
from config.constants import *


class TouchHandler:
    def __init__(self, touch, state, menu_handler):
        self.touch        = touch
        self.state        = state
        self.menu_handler = menu_handler

    def init(self):
        self.touch.init()
        self.touch.Configure_Standby(timeout=5)

    def setup_callback(self, callback):
        self.touch.int_irq(TP_INT, callback)

    def handle_loop(self):
        """Main touch handling loop — runs entirely on the main thread."""
        while True:
            current_time = time.time()
            gesture      = self.touch.Gestures

            # ── Standby ───────────────────────────────────────────────────────
            if self.state.is_standby:
                if gesture != 0:
                    self._wake_from_standby(current_time)
                time.sleep(0.08)
                continue

            # ── WiFi async state machine tick ─────────────────────────────────
            # This is the ONLY place that renders during async WiFi operations.
            # wifi_menu.tick() checks state flags set by background threads
            # and renders on this (main) thread — no race condition possible.
            wifi_menu = self.menu_handler.wifi_menu
            if self.state.wifi_connecting or getattr(self.state, 'pairing_active', False):
                wifi_menu.tick()
                # Still consume/clear gestures so they don't queue up
                if gesture != 0:
                    self.touch.Gestures = 0
                time.sleep(0.15)
                continue

            # ── Scrolling animations ──────────────────────────────────────────
            self._handle_scrolling_animations(current_time)

            # ── Long press ────────────────────────────────────────────────────
            if gesture == GESTURE_LONG_PRESS:
                self._handle_long_press(current_time)
                continue

            # ── Regular gestures ──────────────────────────────────────────────
            if gesture != 0:
                self._handle_gesture(gesture, current_time)

            # ── Standby check ─────────────────────────────────────────────────
            self._check_standby(current_time)

            time.sleep(0.04)

    def _wake_from_standby(self, current_time):
        logging.info("Waking from standby")
        self.state.is_standby         = False
        self.state.last_activity_time = current_time
        self.touch.Stop_Sleep()
        self.touch.Set_Mode(0)
        self.menu_handler.display.wake()
        self.touch.Gestures = 0
        time.sleep(0.3)
        self.menu_handler.render_current_menu()
        self.state.last_gesture      = None
        self.state.last_gesture_time = current_time

    def _handle_scrolling_animations(self, current_time):
        if self.touch.Gestures == 0:
            if current_time - self.state.last_render_time > RENDER_THROTTLE:
                if self.state.in_saved_networks_mode:
                    self.menu_handler.wifi_menu.render_saved_networks()
                    self.state.last_render_time = current_time
                elif self.state.current_menu == MENU_CONFIRM_NETWORK:
                    self.menu_handler.wifi_menu.render_network_confirmation()
                    self.state.last_render_time = current_time

    def _handle_long_press(self, current_time):
        self.touch.Gestures = 0
        logging.info("Long press - returning to main menu")

        # Cancel any ongoing WiFi operation cleanly
        if self.state.wifi_connecting or getattr(self.state, 'pairing_active', False):
            self.menu_handler.wifi_menu._reset_connect_state()
            self.state.pairing_active             = False
            self.state.in_saved_networks_mode     = False
            self.state.saved_networks_list        = []

        time.sleep(0.2)
        self.state.current_menu    = MENU_MAIN
        self.state.selected_option = 0
        self.state.current_page    = 0
        self.state.in_saved_networks_mode = False
        self.menu_handler.render_main_menu()
        self.state.last_gesture      = None
        self.state.last_gesture_time = current_time
        self.state.last_activity_time = current_time
        time.sleep(0.3)

    def _handle_gesture(self, gesture, current_time):
        is_new = (gesture != self.state.last_gesture) or \
                 (current_time - self.state.last_gesture_time > GESTURE_DEBOUNCE)

        if is_new:
            self.touch.Gestures = 0
            logging.info(f"Gesture: {gesture}")
            self.state.last_gesture      = gesture
            self.state.last_gesture_time = current_time
            self.state.last_activity_time = current_time

            self.menu_handler.handle_gesture(gesture)

            self.touch.Gestures = 0
            time.sleep(0.15)
        else:
            self.touch.Gestures = 0

    def _check_standby(self, current_time):
        if not self.state.is_standby and \
           (current_time - self.state.last_activity_time > STANDBY_TIMEOUT):
            logging.info("Entering standby")
            self.state.is_standby = True
            self.menu_handler.display.sleep()
            self.touch.Configure_Standby(timeout=5)
            self.touch.Gestures       = 0
            self.state.last_gesture   = None