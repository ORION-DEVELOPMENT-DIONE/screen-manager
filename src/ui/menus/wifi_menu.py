"""WiFi menu — circular Orion design"""
import time
import logging
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, GREEN, DIM, WHITE, RED, SURFACE, BORDER,
                         font, font_bold, font_emoji,
                         draw_title, draw_divider, draw_buttons, hit_button, CX, CY)
from config.constants import *
from config.themes import WIFI_MENU_EMOJIS

BTN_Y = 163

_OPTIONS = ["Pair Devices", "Change WiFi", "Saved Networks", "Remove WiFi"]
_ICONS   = ["⇄", "↻", "≡", "✗"]


class WiFiMenu(BaseRenderer):
    def __init__(self, display, state, wifi_service):
        super().__init__(display, state)
        self.wifi_service = wifi_service
        self.options      = _OPTIONS

    # ── main WiFi menu ────────────────────────────────────────────────────────

    def render(self):
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        draw_title(draw, "WiFi", "", GREEN)
        draw_divider(draw, 50)

        fb = font_bold(13)
        fr = font(13)
        ef = font_emoji(14)

        count   = len(self.options)
        item_h  = 32
        total_h = count * item_h
        y_start = max(56, CY - total_h // 2 + 4)

        for i, opt in enumerate(self.options):
            sel   = (i == self.state.wifi_selected)
            color = GREEN if sel else WHITE
            icon  = _ICONS[i]

            y = y_start + i * item_h

            if sel:
                draw.rounded_rectangle(
                    [(30, y - 3), (210, y + item_h - 8)],
                    radius=6, fill=SURFACE
                )

            # icon
            draw.text((38, y), icon, font=ef, fill=color)
            # label
            draw.text((62, y), opt, font=fb if sel else fr, fill=color)

        self.show(img)

    # ── network confirmation ──────────────────────────────────────────────────

    def render_network_confirmation(self):
        current_time = time.time()
        network_name = self.state.network_to_connect

        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        draw_title(draw, "Connect?", "", GREEN)
        draw_divider(draw, 50)

        # Scrolling network name
        fr14 = font_bold(14)
        max_chars = 18

        if network_name != self.state.last_selected_network:
            self.state.scroll_offset        = 0
            self.state.last_scroll_time     = current_time
            self.state.last_selected_network = network_name

        if len(network_name) > max_chars:
            display_net = network_name + "  …  " + network_name[:10]
            if current_time - self.state.last_scroll_time > SCROLL_SPEED:
                self.state.scroll_offset = (
                    self.state.scroll_offset + 1) % (len(network_name) + 6)
                self.state.last_scroll_time = current_time
            net_disp = display_net[self.state.scroll_offset:
                                   self.state.scroll_offset + max_chars]
        else:
            net_disp = network_name
            self.state.scroll_offset = 0

        nw = draw.textlength(net_disp, font=fr14)
        draw.text(((240 - nw) // 2, 90), net_disp, font=fr14, fill=GREEN)

        fr11 = font(11)
        hw   = draw.textlength("to this network?", font=fr11)
        draw.text(((240 - hw) // 2, 112), "to this network?", font=fr11, fill=DIM)

        draw_divider(draw, BTN_Y - 10)
        draw_buttons(draw, "Cancel", "Connect", right_color=GREEN, y=BTN_Y)
        self.show(img)

    # ── saved networks ────────────────────────────────────────────────────────

    def render_saved_networks(self):
        current_time = time.time()
        if current_time - self.state.last_render_time < RENDER_THROTTLE:
            return True
        self.state.last_render_time = current_time

        if not self.state.saved_networks_list:
            self.state.saved_networks_list    = self.wifi_service.get_saved_networks()
            self.state.saved_networks_selected = 0

        if not self.state.saved_networks_list:
            self.render_message("No saved\nnetworks")
            time.sleep(2)
            return False

        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        draw_title(draw, "Saved Networks", "", GREEN)
        draw_divider(draw, 50)

        current     = self.wifi_service.get_current_ssid()
        fb          = font_bold(12)
        fr          = font(12)
        display_n   = 4
        item_h      = 32
        sel         = self.state.saved_networks_selected
        start_idx   = max(0, sel - 1)
        end_idx     = min(len(self.state.saved_networks_list), start_idx + display_n)
        y           = 56

        sel_net = self.state.saved_networks_list[sel]
        if sel_net != self.state.last_selected_network:
            self.state.scroll_offset        = 0
            self.state.last_scroll_time     = current_time
            self.state.last_selected_network = sel_net

        for i in range(start_idx, end_idx):
            net      = self.state.saved_networks_list[i]
            is_cur   = current is not None and net == current
            is_sel   = i == sel
            color    = GREEN if is_sel else WHITE

            if is_sel:
                draw.rounded_rectangle(
                    [(25, y - 2), (215, y + item_h - 6)],
                    radius=6, fill=SURFACE
                )
                text = self._scrolling_name(net, is_cur, current_time)
                prefix = "▶ "
            else:
                name   = net[:16] if len(net) > 16 else net
                suffix = " ✓" if is_cur else ""
                text   = "  " + name + suffix
                prefix = ""

            draw.text((30, y), prefix + text, font=fb if is_sel else fr, fill=color)
            y += item_h

        # scroll hint
        if len(self.state.saved_networks_list) > display_n:
            fh = font(10)
            hw = draw.textlength("▲▼", font=fh)
            draw.text(((240 - hw) // 2, 200), "▲▼", font=fh, fill=DIM)

        fh2 = font(10)
        hw2 = draw.textlength("Tap to connect", font=fh2)
        draw.text(((240 - hw2) // 2, 212), "Tap to connect", font=fh2, fill=DIM)

        self.show(img)
        return True

    def _scrolling_name(self, net, is_cur, current_time):
        suffix    = " ✓" if is_cur else ""
        max_chars = 16
        if len(net) > max_chars:
            disp = net + "   " + net[:10]
            if current_time - self.state.last_scroll_time > SCROLL_SPEED:
                self.state.scroll_offset = (
                    self.state.scroll_offset + 1) % (len(net) + 4)
                self.state.last_scroll_time = current_time
            return disp[self.state.scroll_offset:
                         self.state.scroll_offset + max_chars] + suffix
        self.state.scroll_offset = 0
        return net + suffix

    # ── change-WiFi guide ─────────────────────────────────────────────────────

    def _draw_change_wifi_step(self, idx):
        steps = [
            {"title": "Change WiFi",  "icon": "📶",
             "lines": ["Switches your meter", "to a new network.", "", "You will need your", "new WiFi password."],
             "hint": "Swipe ▶ to continue"},
            {"title": "Step 1 / 3",   "icon": "📡",
             "lines": ["Screen connects to", "OrionSetup hotspot", "automatically.", "", "Keep your phone near."],
             "hint": "◀ back   ▶ next"},
            {"title": "Step 2 / 3",   "icon": "📱",
             "lines": ["On your phone go to:", "", "  orion.local:3000", "", "Enter new WiFi info."],
             "hint": "◀ back   ▶ next"},
            {"title": "Step 3 / 3",   "icon": "✅",
             "lines": ["Screen reconnects", "automatically.", "", "Takes ~30 seconds.", "Swipe ▶ to START."],
             "hint": "◀ back   ▶ START"},
        ]
        step = steps[idx]
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        ef   = font_emoji(28)
        ew   = draw.textlength(step["icon"], font=ef)
        draw.text(((240 - ew) // 2, 16), step["icon"], font=ef, fill=GREEN)

        draw_title(draw, step["title"], "", GREEN, title_size=15)

        fr12 = font(12)
        y    = 82
        for line in step["lines"]:
            lw = draw.textlength(line, font=fr12)
            draw.text(((240 - lw) // 2, y), line, font=fr12, fill=WHITE)
            y += 20

        # Progress dots
        n   = len(steps)
        sp  = 16
        sx  = (240 - n * sp) // 2
        for d in range(n):
            cx   = sx + d * sp + 6
            fill = GREEN if d == idx else DIM
            draw.ellipse([cx - 4, 196, cx + 4, 204], fill=fill)

        fh = font(10)
        hw = draw.textlength(step["hint"], font=fh)
        draw.text(((240 - hw) // 2, 210), step["hint"], font=fh, fill=DIM)

        self.show(img)

    def _handle_change_wifi_guide_gesture(self, gesture):
        step      = getattr(self.state, "change_wifi_step", 0)
        num_steps = 4

        if gesture in (GESTURE_LEFT, GESTURE_LONG_PRESS):
            if step > 0:
                self.state.change_wifi_step = step - 1
                self._draw_change_wifi_step(step - 1)
            else:
                self.state.in_change_wifi_guide = False
                self.state.change_wifi_step     = 0
                self.render()
            return None

        if gesture in (GESTURE_RIGHT, GESTURE_TAP):
            if step < num_steps - 1:
                self.state.change_wifi_step = step + 1
                self._draw_change_wifi_step(step + 1)
            else:
                self.state.in_change_wifi_guide = False
                self.state.change_wifi_step     = 0
                self._launch_change_wifi()
            return None

        return None

    def _launch_change_wifi(self):
        from services.network_service import NetworkService
        self.render_message("Connecting to\nOrionSetup...")
        self.render_loading_animation("Switching", 8)
        success, message = NetworkService(self).ensure_orion_connection()
        self.render_message(message)
        time.sleep(2)
        self.render()

    # ── gesture router ────────────────────────────────────────────────────────

    def handle_gesture(self, gesture, touch_device=None):
        if self.state.in_saved_networks_mode:
            return self._handle_saved_networks_gesture(gesture)
        if getattr(self.state, "in_wifi_qr_mode", False):
            return self._handle_qr_mode_gesture(gesture)
        if getattr(self.state, "in_change_wifi_guide", False):
            return self._handle_change_wifi_guide_gesture(gesture)

        if gesture == GESTURE_UP:
            self.state.wifi_selected = (self.state.wifi_selected - 1) % len(self.options)
            self.render()
        elif gesture == GESTURE_DOWN:
            self.state.wifi_selected = (self.state.wifi_selected + 1) % len(self.options)
            self.render()
        elif gesture == GESTURE_TAP:
            return self._handle_wifi_selection()
        elif gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
            return MENU_MAIN
        return None

    def _handle_saved_networks_gesture(self, gesture):
        if gesture == 0:
            return None
        if gesture == GESTURE_UP:
            self.state.saved_networks_selected = (
                self.state.saved_networks_selected - 1
            ) % len(self.state.saved_networks_list)
            self.render_saved_networks()
        elif gesture == GESTURE_DOWN:
            self.state.saved_networks_selected = (
                self.state.saved_networks_selected + 1
            ) % len(self.state.saved_networks_list)
            self.render_saved_networks()
        elif gesture == GESTURE_TAP:
            self.state.network_to_connect     = self.state.saved_networks_list[
                self.state.saved_networks_selected]
            self.state.in_saved_networks_mode = False
            return MENU_CONFIRM_NETWORK
        elif gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
            self.state.in_saved_networks_mode = False
            self.state.saved_networks_list    = []
            return MENU_WIFI
        return None

    def _handle_qr_mode_gesture(self, gesture):
        if gesture == GESTURE_LEFT:
            self.state.in_wifi_qr_mode = False
            return MENU_WIFI
        return None

    def handle_confirmation_gesture(self, gesture, touch_device):
        if gesture == 0:
            return None
        if gesture == GESTURE_LONG_PRESS:
            self.state.in_saved_networks_mode = True
            return MENU_WIFI
        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            action = hit_button(x, y, btn_y=BTN_Y)

            if action == "left":   # Cancel
                self.state.in_saved_networks_mode = True
                time.sleep(0.2)
                return MENU_WIFI

            if action == "right":  # Connect
                if self.wifi_service.connect_to_saved_network(
                        self.state.network_to_connect):
                    self.render_message("✅ Connected")
                else:
                    self.render_message("❌ Failed")
                time.sleep(2)
                self.state.in_saved_networks_mode = False
                self.state.saved_networks_list    = []
                return MENU_WIFI
        return None

    def _handle_wifi_selection(self):
        time.sleep(0.1)
        sel = self.state.wifi_selected
        if sel == 0:
            self._handle_pair_devices()
        elif sel == 1:
            self.state.in_change_wifi_guide = True
            self.state.change_wifi_step     = 0
            self._draw_change_wifi_step(0)
        elif sel == 2:
            self.state.in_saved_networks_mode  = True
            self.state.saved_networks_list     = self.wifi_service.get_saved_networks()
            self.state.saved_networks_selected = 0
            if not self.render_saved_networks():
                self.state.in_saved_networks_mode = False
            time.sleep(0.2)
        elif sel == 3:
            self._handle_remove_wifi()
        return None

    def _handle_pair_devices(self):
        from services.network_service import NetworkService
        self.render_loading_animation("Pairing", 2)
        success, message = NetworkService(self).ensure_orion_connection()
        self.render_message(message)
        time.sleep(2)
        self.render()

    def _handle_remove_wifi(self):
        current = self.wifi_service.get_current_ssid()
        if current:
            self.render_message(f"Removing\n{current}...")
            if self.wifi_service.disconnect_wifi():
                self.render_message("✅ WiFi removed")
            else:
                self.render_message("❌ Failed to\nremove")
        else:
            self.render_message("No active\nconnection")
        time.sleep(2)
        self.render()

    def render_qr_code(self):
        import qrcode
        url       = "http://orion.local:3000"
        qr        = qrcode.make(url)
        img       = self.canvas()
        qr_size   = 140
        qr_r      = qr.resize((qr_size, qr_size))
        img.paste(qr_r, ((240 - qr_size) // 2, 30))
        draw = ImageDraw.Draw(img)
        f    = font(12)
        uw   = draw.textlength(url, font=f)
        draw.text(((240 - uw) // 2, 176), url, font=f, fill=GREEN)
        self.show(img)