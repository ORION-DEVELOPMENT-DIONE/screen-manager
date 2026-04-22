"""
Confirmation & Power menus — Dione/Orion circular design

Flow:
  Main Menu → "Shutdown" → MENU_POWER_OPTIONS (Restart / Power Off)
    → tap Restart  → MENU_CONFIRM_RESTART  (Cancel / Restart)
    → tap Power Off → MENU_CONFIRM_SHUTDOWN (Cancel / Shut Down)

"""
import os
import time
import logging
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold, font_emoji,
                         draw_divider, draw_buttons, hit_button,
                         CX, CY, SAFE_W)
from config.constants import *
 
 
# ── Big button layout for power options ───────────────────────────────────────
_BTN_W      = 170
_BTN_H      = 58
_BTN_GAP    = 12
_BTN_RADIUS = 14
_BTN_X      = (240 - _BTN_W) // 2
_BTN1_Y     = 68
_BTN2_Y     = _BTN1_Y + _BTN_H + _BTN_GAP
 
# Confirmation button Y
_CONF_BTN_Y = 167
 
 
class ConfirmationMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)
        self._wifi_service = None   # set lazily for remove-wifi action
 
    # ══════════════════════════════════════════════════════════════════════════
    # SCREEN 1: Power Options — two big buttons (Restart / Power Off)
    # ══════════════════════════════════════════════════════════════════════════
 
    def render_power_options(self):
        T   = self._theme()
        img = self.canvas()
        draw = ImageDraw.Draw(img)
 
        self.draw_title(draw, "Power", title_size=17)
        draw_divider(draw, 52, T)
 
        ef   = font_emoji(22)
        fb16 = font_bold(16)
 
        # ── Restart button ────────────────────────────────────────────────
        restart_color = T["CYAN"]
        inner_restart = tuple(min(255, c // 6) for c in restart_color)
        draw.rounded_rectangle(
            [(_BTN_X, _BTN1_Y), (_BTN_X + _BTN_W, _BTN1_Y + _BTN_H)],
            radius=_BTN_RADIUS, fill=inner_restart,
            outline=restart_color, width=2
        )
 
        icon = "↻"
        label = "Restart"
        iw = draw.textlength(icon, font=ef)
        lw = draw.textlength(label, font=fb16)
        total_w = iw + 8 + lw
        start_x = _BTN_X + (_BTN_W - total_w) // 2
        text_y  = _BTN1_Y + (_BTN_H - 18) // 2
 
        draw.text((int(start_x), text_y - 2), icon, font=ef, fill=restart_color)
        draw.text((int(start_x + iw + 8), text_y), label, font=fb16, fill=restart_color)
 
        # ── Power Off button ──────────────────────────────────────────────
        off_color = T["RED"]
        inner_off = tuple(min(255, c // 6) for c in off_color)
        draw.rounded_rectangle(
            [(_BTN_X, _BTN2_Y), (_BTN_X + _BTN_W, _BTN2_Y + _BTN_H)],
            radius=_BTN_RADIUS, fill=inner_off,
            outline=off_color, width=2
        )
 
        icon2  = "⏻"
        label2 = "Power Off"
        i2w = draw.textlength(icon2, font=ef)
        l2w = draw.textlength(label2, font=fb16)
        total_w2 = i2w + 8 + l2w
        start_x2 = _BTN_X + (_BTN_W - total_w2) // 2
        text_y2  = _BTN2_Y + (_BTN_H - 18) // 2
 
        draw.text((int(start_x2), text_y2 - 2), icon2, font=ef, fill=off_color)
        draw.text((int(start_x2 + i2w + 8), text_y2), label2, font=fb16, fill=off_color)
 
        # Hint
        fh = font(10)
        hint = "Swipe \u2190 back"
        hw = draw.textlength(hint, font=fh)
        draw.text(((240 - hw) // 2, 212), hint, font=fh, fill=T["DIM"])
 
        self.show(img)
 
    def handle_power_options_gesture(self, gesture, touch_device):
        if gesture in (GESTURE_LEFT, GESTURE_LONG_PRESS):
            return MENU_MAIN
 
        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
 
            if (_BTN_X <= x <= _BTN_X + _BTN_W and
                    _BTN1_Y <= y <= _BTN1_Y + _BTN_H):
                return MENU_CONFIRM_RESTART
 
            if (_BTN_X <= x <= _BTN_X + _BTN_W and
                    _BTN2_Y <= y <= _BTN2_Y + _BTN_H):
                return MENU_CONFIRM_SHUTDOWN
 
        return None
 
    # ══════════════════════════════════════════════════════════════════════════
    # SCREEN 2: Shutdown Confirmation
    # ══════════════════════════════════════════════════════════════════════════
 
    def render_shutdown_confirmation(self):
        T   = self._theme()
        img = self.canvas()
        draw = ImageDraw.Draw(img)
 
        ef = font_emoji(28)
        ew = draw.textlength("\u23fb", font=ef)
        draw.text(((240 - ew) // 2, 28), "\u23fb", font=ef, fill=T["RED"])
 
        fb = font_bold(17)
        txt = "Power Off?"
        tw = draw.textlength(txt, font=fb)
        draw.text(((240 - tw) // 2, 66), txt, font=fb, fill=T["RED"])
 
        fr = font(13)
        sub = "Orion will shut down"
        sw = draw.textlength(sub, font=fr)
        draw.text(((240 - sw) // 2, 90), sub, font=fr, fill=T["DIM"])
 
        draw_divider(draw, _CONF_BTN_Y - 12, T)
        draw_buttons(draw, "Cancel", "Power Off",
                     right_color=T["RED"], theme=T, y=_CONF_BTN_Y)
        self.show(img)
 
    def handle_shutdown_gesture(self, gesture, touch_device):
        if gesture in (GESTURE_LONG_PRESS, GESTURE_LEFT):
            return MENU_POWER_OPTIONS
 
        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            action = hit_button(x, y, btn_y=_CONF_BTN_Y)
            if action == "left":
                return MENU_POWER_OPTIONS
            if action == "right":
                self.render_message("Shutting\ndown...")
                time.sleep(2)
                os.system("sudo shutdown now")
 
        return None
 
    # ══════════════════════════════════════════════════════════════════════════
    # SCREEN 3: Restart Confirmation
    # ══════════════════════════════════════════════════════════════════════════
 
    def render_restart_confirmation(self):
        T   = self._theme()
        img = self.canvas()
        draw = ImageDraw.Draw(img)
 
        ef = font_emoji(28)
        icon = "\u21bb"
        ew = draw.textlength(icon, font=ef)
        draw.text(((240 - ew) // 2, 28), icon, font=ef, fill=T["CYAN"])
 
        fb = font_bold(17)
        txt = "Restart?"
        tw = draw.textlength(txt, font=fb)
        draw.text(((240 - tw) // 2, 66), txt, font=fb, fill=T["CYAN"])
 
        fr = font(13)
        sub = "Orion will reboot"
        sw = draw.textlength(sub, font=fr)
        draw.text(((240 - sw) // 2, 90), sub, font=fr, fill=T["DIM"])
 
        draw_divider(draw, _CONF_BTN_Y - 12, T)
        draw_buttons(draw, "Cancel", "Restart",
                     right_color=T["CYAN"], theme=T, y=_CONF_BTN_Y)
        self.show(img)
 
    def handle_restart_gesture(self, gesture, touch_device):
        if gesture in (GESTURE_LONG_PRESS, GESTURE_LEFT):
            return MENU_POWER_OPTIONS
 
        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            action = hit_button(x, y, btn_y=_CONF_BTN_Y)
            if action == "left":
                return MENU_POWER_OPTIONS
            if action == "right":
                self.render_message("Restarting...")
                time.sleep(2)
                os.system("sudo reboot")
 
        return None
 
    # ══════════════════════════════════════════════════════════════════════════
    # SCREEN 4: Remove WiFi Confirmation
    # ══════════════════════════════════════════════════════════════════════════
 
    def render_remove_wifi_confirmation(self):
        T   = self._theme()
        img = self.canvas()
        draw = ImageDraw.Draw(img)
 
        # WiFi icon
        ef = font_emoji(28)
        icon = "\u2718"    # ✘ cross mark
        ew = draw.textlength(icon, font=ef)
        draw.text(((240 - ew) // 2, 28), icon, font=ef, fill=T["ORANGE"])
 
        # Title
        fb = font_bold(17)
        txt = "Remove WiFi?"
        tw = draw.textlength(txt, font=fb)
        draw.text(((240 - tw) // 2, 66), txt, font=fb, fill=T["ORANGE"])
 
        # Current SSID if available
        fr = font(13)
        ssid = self._get_current_ssid()
        if ssid:
            # Show SSID name
            ssid_display = ssid if len(ssid) <= 18 else ssid[:16] + ".."
            sw = draw.textlength(ssid_display, font=font_bold(13))
            draw.text(((240 - sw) // 2, 90), ssid_display,
                      font=font_bold(13), fill=T["WHITE"])
            # Subtitle below
            sub = "will be forgotten"
            sw2 = draw.textlength(sub, font=fr)
            draw.text(((240 - sw2) // 2, 110), sub, font=fr, fill=T["DIM"])
        else:
            sub = "No WiFi connected"
            sw = draw.textlength(sub, font=fr)
            draw.text(((240 - sw) // 2, 95), sub, font=fr, fill=T["DIM"])
 
        draw_divider(draw, _CONF_BTN_Y - 12, T)
        draw_buttons(draw, "Cancel", "Remove",
                     right_color=T["ORANGE"], theme=T, y=_CONF_BTN_Y)
        self.show(img)
 
    def handle_remove_wifi_gesture(self, gesture, touch_device):
        if gesture in (GESTURE_LONG_PRESS, GESTURE_LEFT):
            return MENU_WIFI
 
        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            action = hit_button(x, y, btn_y=_CONF_BTN_Y)
            if action == "left":
                return MENU_WIFI
            if action == "right":
                self._do_remove_wifi()
                return MENU_WIFI
 
        return None
 
    def _get_current_ssid(self):
        """Get current SSID from wifi_service via state/menu_handler."""
        try:
            # Access wifi_service through the menu handler chain
            if self._wifi_service:
                return self._wifi_service.get_current_ssid()
            # Fallback: try to read from state
            if hasattr(self.state, 'current_ssid'):
                return self.state.current_ssid
        except Exception:
            pass
        return None
 
    def _do_remove_wifi(self):
        """Actually remove the WiFi network and show result."""
        try:
            ssid = self._get_current_ssid()
            if ssid and self._wifi_service:
                self._wifi_service.remove_network(ssid)
                self.render_message(f"Removed\n{ssid[:16]}")
            elif not ssid:
                self.render_message("No WiFi\nconnected")
            else:
                self.render_message("No WiFi\nservice")
        except Exception as e:
            logging.error(f"Remove WiFi error: {e}")
            self.render_message("Error\nremoving")
        time.sleep(2)
 
    def set_wifi_service(self, wifi_service):
        """Set wifi_service reference — called during MenuHandler init."""
        self._wifi_service = wifi_service