"""Main menu — Dione/Orion circular design v4 (scrollable)"""
import time
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold, font_emoji,
                         draw_status_bar, draw_corner_hash, CX)
from config.constants import *
from config.themes import THEMES

VISIBLE  = 4       # items visible at once
ITEM_H   = 36      # bigger items
THEME_Y  = 200     # theme toggle position (fixed at bottom)


class MainMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)
        self.base_items = [
            "Energy", "Device", "WiFi Setup",
            "Dashboard", "Update", "Shutdown"
        ]
        self._viewport_top = 0   # index of first visible item

    def get_items(self):
        return [
            "(1) Update" if item == "Update" and self.state.update_available else item
            for item in self.base_items
        ]

    def _ensure_visible(self, items):
        """Shift viewport so selected_option is visible."""
        sel = self.state.selected_option
        if sel < self._viewport_top:
            self._viewport_top = sel
        elif sel >= self._viewport_top + VISIBLE:
            self._viewport_top = sel - VISIBLE + 1
        # Clamp
        max_top = max(0, len(items) - VISIBLE)
        self._viewport_top = max(0, min(self._viewport_top, max_top))

    def render(self):
        T     = self._theme()
        img   = self.canvas()
        draw  = ImageDraw.Draw(img)
        items = self.get_items()
        count = len(items)
        self._ensure_visible(items)

        # Status bar
        wifi_ok  = getattr(self.state, "wifi_connected", False)
        meter_ok = getattr(self.state, "meter_paired",   False)
        draw_status_bar(draw, wifi_ok, meter_ok, T)

        # ── Visible items ─────────────────────────────────────────────────
        fb = font_bold(20)
        fr = font(19)
        y_start = 50
        vt = self._viewport_top

        for vi in range(VISIBLE):
            idx = vt + vi
            if idx >= count:
                break

            item     = items[idx]
            selected = (idx == self.state.selected_option)
            is_alert = item.startswith("(1)")
            color    = T["ORANGE"] if is_alert else (T["CYAN"] if selected else T["WHITE"])
            f_use    = fb if selected else fr
            prefix   = "▶ " if selected else "  "
            text     = prefix + item
            tw       = draw.textlength(text, font=f_use)
            x        = (240 - tw) // 2
            y        = y_start + vi * ITEM_H

            if selected:
                draw.rounded_rectangle(
                    [(x - 10, y - 4), (x + tw + 10, y + 22)],
                    radius=8, fill=T["SURFACE"]
                )
            draw.text((x, y), text, font=f_use, fill=color)
            
        # ── Scroll indicator dots (right edge) ───────────────────────────
        if count > VISIBLE:
            dot_x  = 218
            dot_gap = 10
            total_dots = count
            dot_start_y = y_start + (VISIBLE * ITEM_H) // 2 - (total_dots * dot_gap) // 2

            for i in range(total_dots):
                dy = dot_start_y + i * dot_gap
                is_sel = (i == self.state.selected_option)
                if is_sel:
                    draw.ellipse([(dot_x - 3, dy - 3), (dot_x + 3, dy + 3)], fill=T["ORANGE"])
                else:
                    draw.ellipse([(dot_x - 2, dy - 2), (dot_x + 2, dy + 2)],
                                 outline=T["DIM"], width=1)

            # Scroll arrows
            fa = font(12)
            if vt > 0:
                draw.text((214, y_start - 16), "▲", font=fa, fill=T["ORANGE"])
            if vt + VISIBLE < count:
                draw.text((214, y_start + VISIBLE * ITEM_H - 4), "▼", font=fa, fill=T["ORANGE"])

        # ── Theme toggle (fixed at bottom) ────────────────────────────────
        ef  = font_emoji(22)
        emo = "🌗"
        ew  = draw.textlength(emo, font=ef)
        draw.rounded_rectangle(
            [(int(CX - ew//2) - 8, THEME_Y - 3),
             (int(CX + ew//2) + 8, THEME_Y + 25)],
            radius=6, fill=T["SURFACE"]
        )
        draw.text(((240 - ew) // 2, THEME_Y), emo, font=ef, fill=T["CYAN"])

        self.show(img)

    def handle_gesture(self, gesture, touch_device=None):
        items = self.get_items()
        count = len(items)

        if gesture == GESTURE_UP:
            self.state.selected_option = (self.state.selected_option - 1) % count
            self.render()
        elif gesture == GESTURE_DOWN:
            self.state.selected_option = (self.state.selected_option + 1) % count
            self.render()
        elif gesture == GESTURE_TAP:
            return self._handle_selection(touch_device)
        return None

    def _handle_selection(self, touch_device):
        # Check theme toggle tap
        if touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            ef   = font_emoji(22)
            ew   = ef.getlength("🌗")
            ex0  = int(CX - ew//2) - 10
            ex1  = int(CX + ew//2) + 10
            if THEME_Y - 5 <= y <= THEME_Y + 28 and ex0 <= x <= ex1:
                from utils.state import save_theme
                new_name = "light" if self.state.active_theme.name == "dark" else "dark"
                self.state.active_theme = THEMES[new_name]
                save_theme(new_name)
                self.display.invalidate_background_cache()
                self.render()
                time.sleep(0.2)
                return None

        time.sleep(0.1)
        menu_map = {
            0: MENU_MQTT, 1: MENU_METRICS,
            2: MENU_WIFI, 3: MENU_DASHBOARD,
            4: MENU_UPDATE, 5: MENU_POWER_OPTIONS
        }
        return menu_map.get(self.state.selected_option)