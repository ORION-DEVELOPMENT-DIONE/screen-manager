"""Confirmation dialogs — Dione/Orion circular design v3"""
import os
import time
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold, font_emoji,
                         draw_divider, draw_buttons, hit_button)
from config.constants import *

BTN_Y = 167
CX = CY = 120


class ConfirmationMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)

    def render_shutdown_confirmation(self):
        T    = self._theme()
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        # Power icon — using Symbola font, sized to not overlap text
        ef  = font_emoji(28)
        ew  = draw.textlength("⏻", font=ef)
        # Place icon at top — y=28 so it doesn't crowd the text
        draw.text(((240 - ew) // 2, 28), "⏻", font=ef, fill=T["RED"])

        # Title — below icon with breathing room
        fb  = font_bold(17)
        txt = "Shut Down?"
        tw  = draw.textlength(txt, font=fb)
        draw.text(((240 - tw) // 2, 66), txt, font=fb, fill=T["RED"])

        # Subtitle
        fr  = font(14)
        sub = "This will power off Orion"
        sw  = draw.textlength(sub, font=fr)
        draw.text(((240 - sw) // 2, 88), sub, font=fr, fill=T["DIM"])

        draw_divider(draw, BTN_Y - 12, T)
        draw_buttons(draw, "Cancel", "Shut Down",
                     right_color=T["RED"], theme=T, y=BTN_Y)
        self.show(img)

    def handle_shutdown_gesture(self, gesture, touch_device):
        if gesture == GESTURE_LONG_PRESS:
            return MENU_MAIN

        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y   = touch_device.X_point, touch_device.Y_point
            action = hit_button(x, y, btn_y=BTN_Y)
            if action == "left":
                return MENU_MAIN
            if action == "right":
                self.render_message("Shutting\ndown...")
                time.sleep(2)
                os.system("sudo shutdown now")

        return None

    def _draw_yes_no_buttons(self, draw):
        T = self._theme()
        draw_buttons(draw, "No", "Yes",
                     right_color=T["CYAN"], theme=T, y=BTN_Y)