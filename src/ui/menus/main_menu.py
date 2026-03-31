"""Main menu — circular Orion design"""
import time
from PIL import ImageDraw
from ui.renderer import BaseRenderer, GREEN, ORANGE, DIM, WHITE, SURFACE, BORDER, font, font_bold, font_emoji, draw_status_dots
from config.constants import *
from config.themes import THEMES

ITEMS      = ["Energy", "Device", "WiFi Setup", "Update", "Shutdown"]
ITEM_H     = 30
THEME_Y    = 196


class MainMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)
        self.base_items = ITEMS

    def get_items(self):
        out = []
        for item in self.base_items:
            if item == "Update" and self.state.update_available:
                out.append("(1) Update")
            else:
                out.append(item)
        return out

    def render(self):
        img   = self.canvas()
        draw  = ImageDraw.Draw(img)
        items = self.get_items()

        # Status dots
        wifi_ok  = getattr(self.state, "wifi_connected", False)
        meter_ok = getattr(self.state, "meter_paired",   False)
        draw_status_dots(draw, wifi_ok, meter_ok)

        # Menu items — vertically centred in safe zone below dots
        count   = len(items)
        total_h = count * ITEM_H
        y_start = max(42, (200 - total_h) // 2 + 10)

        fb = font_bold(15)
        fr = font(15)

        for i, item in enumerate(items):
            selected = (i == self.state.selected_option)
            is_update_alert = item.startswith("(1)")

            if is_update_alert:
                color = ORANGE
            elif selected:
                color = GREEN
            else:
                color = WHITE

            prefix = "▶ " if selected else "  "
            text   = prefix + item
            tw     = draw.textlength(text, font=fb if selected else fr)
            x      = (240 - tw) // 2
            y      = y_start + i * ITEM_H

            # Highlight pill for selected item
            if selected:
                draw.rounded_rectangle(
                    [(x - 8, y - 3), (x + tw + 8, y + ITEM_H - 6)],
                    radius=6, fill=SURFACE
                )

            draw.text((x, y), text, font=fb if selected else fr, fill=color)

        # Theme toggle
        ef   = font_emoji(22)
        emo  = "🌗"
        ew   = draw.textlength(emo, font=ef)
        draw.text(((240 - ew) // 2, THEME_Y), emo, font=ef, fill=DIM)

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

            # Theme toggle hit area
            ef    = font_emoji(22)
            img_  = self.canvas()
            draw_ = ImageDraw.Draw(img_)
            ew    = draw_.textlength("🌗", font=ef)
            ex0   = (240 - ew) // 2 - 8
            ex1   = (240 + ew) // 2 + 8
            if THEME_Y - 4 <= y <= THEME_Y + 26 and ex0 <= x <= ex1:
                self.state.active_theme = (
                    THEMES["light"] if self.state.active_theme.name == "dark"
                    else THEMES["dark"]
                )
                self.display.invalidate_background_cache()
                self.render()
                time.sleep(0.2)
                return None

        time.sleep(0.1)
        menu_map = {0: MENU_MQTT, 1: MENU_METRICS,
                    2: MENU_WIFI, 3: MENU_UPDATE, 4: MENU_CONFIRM_SHUTDOWN}
        return menu_map.get(self.state.selected_option)