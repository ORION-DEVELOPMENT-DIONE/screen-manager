"""Main menu rendering and handling"""
import time
from PIL import ImageDraw
from ui.renderer import BaseRenderer
from config.constants import *
from config.themes import TOGGLE_THEME_EMOJI, THEMES

ITEM_HEIGHT  = 28
ITEMS_COUNT  = 5
MENU_Y_START = (SCREEN_HEIGHT - ITEMS_COUNT * ITEM_HEIGHT) // 2  # 50

# Status dots — top-centre, raised so they don't crowd the menu
# y=15: safe x = 66..174  (W=110, M=130 both comfortably inside)
# label y=23: safe x = 59..181
DOT_R   = 5
DOT_Y   = 20
W_CX    = 110
M_CX    = 130
LABEL_Y = DOT_Y + DOT_R + 3   # 23

# Theme toggle — moved up from y=210, bigger font
THEME_Y         = 200
THEME_FONT_SIZE = 28


class MainMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)
        self.base_items = ["Energy", "Device", "WiFi Setup", "Update", "Shutdown"]

    def get_items(self):
        items = []
        for item in self.base_items:
            if item == "Update" and self.state.update_available:
                items.append("(1) Update")
            else:
                items.append(item)
        return items

    def render(self):
        image = self.get_background()
        draw  = ImageDraw.Draw(image)

        items = self.get_items()

        for i, item in enumerate(items):
            is_selected = (i == self.state.selected_option)
            if item.startswith("(1) Update"):
                color = "orange" if not is_selected else self.get_selected_color()
            else:
                color = self.get_selected_color() if is_selected else self.get_text_color()

            prefix       = "➤ " if is_selected else "  "
            display_text = prefix + item
            text_w = self.get_font().getlength(display_text)
            x = (SCREEN_WIDTH - text_w) // 2
            y = MENU_Y_START + i * ITEM_HEIGHT
            draw.text((x, y), display_text, fill=color, font=self.get_font())

        # Theme toggle — bigger, moved up
        theme_font  = self.get_font(THEME_FONT_SIZE)
        emoji_w = theme_font.getlength(TOGGLE_THEME_EMOJI)
        emoji_font = self.get_emoji_font(THEME_FONT_SIZE)
        emoji_w = emoji_font.getlength(TOGGLE_THEME_EMOJI)
        draw.text(((SCREEN_WIDTH - emoji_w) // 2, THEME_Y), TOGGLE_THEME_EMOJI,
                  fill=self.get_selected_color(), font=emoji_font)
        # Status dots — always on top
        self._draw_status_bar(draw)

        self.display.show_image(image)
        del draw, image

    def _draw_status_bar(self, draw):
        wifi_ok  = getattr(self.state, "wifi_connected", False)
        meter_ok = getattr(self.state, "meter_paired",   False)

        wifi_color  = "#2ECC71" if wifi_ok  else "#E74C3C"
        meter_color = "#2ECC71" if meter_ok else "#E74C3C"

        icon_font = self.get_emoji_font(20)

        # WiFi icon — left of centre
        wifi_w = icon_font.getlength("📶")
        draw.text((105 - wifi_w // 2, 10), "📶", font=icon_font, fill=wifi_color)

        # Meter/power icon — right of centre
        bolt_w = icon_font.getlength("⚡")
        draw.text((135 - bolt_w // 2, 10), "⚡", font=icon_font, fill=meter_color)

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

            # Theme toggle hit area — matches new y=196, font size 28
            theme_font    = self.get_font(THEME_FONT_SIZE)
            emoji_w       = theme_font.getlength(TOGGLE_THEME_EMOJI)
            emoji_x_start = (SCREEN_WIDTH - emoji_w) // 2 - 10
            emoji_x_end   = (SCREEN_WIDTH + emoji_w) // 2 + 10
            emoji_y_start = THEME_Y - 4
            emoji_y_end   = THEME_Y + THEME_FONT_SIZE + 4

            if (emoji_y_start <= y <= emoji_y_end and
                    emoji_x_start <= x <= emoji_x_end):
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
            0: MENU_MQTT,
            1: MENU_METRICS,
            2: MENU_WIFI,
            3: MENU_UPDATE,
            4: MENU_CONFIRM_SHUTDOWN,
        }
        return menu_map.get(self.state.selected_option)