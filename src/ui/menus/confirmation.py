"""Confirmation dialogs — circular Orion design"""
import os
import time
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, GREEN, RED, DIM, WHITE, SURFACE,
                         font, font_bold, font_emoji,
                         draw_title, draw_divider, draw_buttons, hit_button)
from config.constants import *

BTN_Y = 163


class ConfirmationMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)

    def render_shutdown_confirmation(self):
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        # Icon
        ef  = font_emoji(32)
        ew  = draw.textlength("⏻", font=ef)
        draw.text(((240 - ew) // 2, 38), "⏻", font=ef, fill=RED)

        # Title
        draw_title(draw, "Shut Down?",
                   "This will power off Orion", RED,
                   title_size=17, sub_size=10)

        draw_divider(draw, BTN_Y - 10)
        draw_buttons(draw, "Cancel", "Shut Down", right_color=RED, y=BTN_Y)

        self.show(img)

    def handle_shutdown_gesture(self, gesture, touch_device):
        if gesture == GESTURE_LONG_PRESS:
            return MENU_MAIN

        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            action = hit_button(x, y, btn_y=BTN_Y)

            if action == "left":   # Cancel
                return MENU_MAIN
            if action == "right":  # Shut Down
                self.render_message("Shutting\ndown...", color=RED)
                time.sleep(2)
                os.system("sudo shutdown now")

        return None