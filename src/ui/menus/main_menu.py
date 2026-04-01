"""Main menu — Dione/Orion circular design v3"""
import time
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold, font_emoji,
                         draw_status_bar, draw_corner_hash, DARK, LIGHT, CX)
from config.constants import *
from config.themes import THEMES

ITEM_H  = 29
THEME_Y =195


class MainMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)
        self.base_items = ["Energy", "Device", "WiFi Setup", "Update", "Shutdown"]

    def get_items(self):
        return [
            "(1) Update" if item == "Update" and self.state.update_available else item
            for item in self.base_items
        ]

    def render(self):
        T     = self._theme()
        img   = self.canvas()
        draw  = ImageDraw.Draw(img)
        items = self.get_items()

        # Emoji status bar — 📶 ⚡
        wifi_ok  = getattr(self.state, "wifi_connected", False)
        meter_ok = getattr(self.state, "meter_paired",   False)
        draw_status_bar(draw, wifi_ok, meter_ok, T)

        # Menu items — centred in safe zone
        count   = len(items)
        total_h = count * ITEM_H
        y_start = max(47, (196 - total_h) // 2 + 8)

        fb = font_bold(17)
        fr = font(16)

        for i, item in enumerate(items):
            selected        = (i == self.state.selected_option)
            is_update_alert = item.startswith("(1)")

            color = T["ORANGE"] if is_update_alert else (T["CYAN"] if selected else T["WHITE"])
            f_use = fb if selected else fr
            prefix = "▶ " if selected else "  "
            text   = prefix + item
            tw     = draw.textlength(text, font=f_use)
            x      = (240 - tw) // 2
            y      = y_start + i * ITEM_H

            if selected:
                draw.rounded_rectangle(
                    [(x - 8, y - 3), (x + tw + 8, y + 19)],
                    radius=7, fill=T["SURFACE"]
                )
            draw.text((x, y), text, font=f_use, fill=color)

        # Theme toggle — emoji with cyan color so it's visible
        ef  = font_emoji(22)
        emo = "🌗"
        ew  = draw.textlength(emo, font=ef)
        # Draw a small pill behind it so it's always visible
        draw.rounded_rectangle(
            [(int(CX - ew//2) - 8, THEME_Y - 3),
             (int(CX + ew//2) + 8, THEME_Y + 25)],
            radius=6, fill=T["SURFACE"]
        )
        draw.text(((240 - ew) // 2, THEME_Y), emo, font=ef, fill=T["CYAN"])

        self.show(img)

    def handle_gesture(self, gesture, touch_device=None):
        items = self.get_items()
        if gesture == GESTURE_UP:
            self.state.selected_option = (self.state.selected_option - 1) % len(items)
            self.render()
        elif gesture == GESTURE_DOWN:
            self.state.selected_option = (self.state.selected_option + 1) % len(items)
            self.render()
        elif gesture == GESTURE_TAP:
            return self._handle_selection(touch_device)
        return None

    def _handle_selection(self, touch_device):
        if touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            ef   = font_emoji(22)
            ew   = ef.getlength("🌗")
            ex0  = int(CX - ew//2) - 10
            ex1  = int(CX + ew//2) + 10
            if THEME_Y - 5 <= y <= THEME_Y + 28 and ex0 <= x <= ex1:
                self.state.active_theme = (
                    THEMES["light"] if self.state.active_theme.name == "dark"
                    else THEMES["dark"]
                )
                self.display.invalidate_background_cache()
                self.render()
                time.sleep(0.2)
                return None

        time.sleep(0.1)
        menu_map = {
            0: MENU_MQTT, 1: MENU_METRICS,
            2: MENU_WIFI, 3: MENU_UPDATE, 4: MENU_CONFIRM_SHUTDOWN
        }
        return menu_map.get(self.state.selected_option)