"""WiFi menu — Dione/Orion circular design v3
Thread-safety fix:
  - Background threads NEVER call render() or show_image()
  - They only write to state flags
  - The main touch loop reads those flags and renders safely
"""
import time
import threading
import logging
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold, font_emoji,
                         draw_divider, draw_buttons, hit_button,
                         draw_nav_arrows, draw_page_indicator)
from config.constants import *
from config.themes import WIFI_MENU_EMOJIS

BTN_Y             = 167
MESSAGE_DISPLAY_S = 3
_OPTIONS = ["Pair Devices", "Change WiFi", "Saved Networks", "Remove WiFi"]
_ICONS   = ["⇄", "↻", "≡", "✗"]
CX = CY  = 120


class WiFiMenu(BaseRenderer):
    def __init__(self, display, state, wifi_service):
        super().__init__(display, state)
        self.wifi_service = wifi_service
        self.options      = _OPTIONS

        # Ensure state has the connect-flow attributes
        if not hasattr(state, 'wifi_connecting'):
            state.wifi_connecting     = False
        if not hasattr(state, 'wifi_connect_status'):
            state.wifi_connect_status = ""
        if not hasattr(state, 'wifi_connect_result'):
            state.wifi_connect_result = None
        if not hasattr(state, 'wifi_result_shown_at'):
            state.wifi_result_shown_at = 0.0
        if not hasattr(state, 'pairing_active'):
            state.pairing_active = False

    # ── main render ───────────────────────────────────────────────────────────

    def render(self):
        T    = self._theme()
        img  = self.canvas()
        draw = ImageDraw.Draw(img)
        self.draw_title(draw, "WiFi", title_size=17)
        draw_divider(draw, 52, T)

        fb = font_bold(14); fr = font(14)
        item_h  = 33
        total_h = len(self.options) * item_h
        y_start = max(58, CY - total_h // 2 + 4)

        for i, (opt, icon) in enumerate(zip(self.options, _ICONS)):
            sel   = (i == self.state.wifi_selected)
            color = T["CYAN"] if sel else T["WHITE"]
            y     = y_start + i * item_h
            if sel:
                draw.rounded_rectangle(
                    [(28, y - 3), (212, y + item_h - 8)],
                    radius=7, fill=T["SURFACE"])
            draw.text((36, y), icon, font=fb if sel else fr, fill=color)
            draw.text((58, y), opt,  font=fb if sel else fr, fill=color)
        self.show(img)

    def render_connecting_status(self):
        """Called by main loop while wifi_connecting is True."""
        self.render_message(self.state.wifi_connect_status)

    def render_connect_result(self):
        """Called by main loop once when wifi_connect_result is set."""
        success, msg = self.state.wifi_connect_result
        T     = self._theme()
        color = T["CYAN"] if success else T["RED"]
        self.render_message(msg, color=color)
        self.state.wifi_result_shown_at = time.time()

    def tick(self):
        """
        Called every main-loop cycle when current_menu == MENU_WIFI
        or MENU_CONFIRM_NETWORK.
        Handles the connect-flow state machine without any background rendering.
        Returns a menu constant to navigate to, or None to stay.
        """
        # ── async connect in progress ─────────────────────────────────────────
        if self.state.wifi_connecting:
            if self.state.wifi_connect_result is None:
                # Still running — update status display
                self.render_connecting_status()
                return None

            # Result just arrived — show it once
            if self.state.wifi_result_shown_at == 0.0:
                self.render_connect_result()
                return None

            # Result has been shown — wait MESSAGE_DISPLAY_S then clean up
            if time.time() - self.state.wifi_result_shown_at >= MESSAGE_DISPLAY_S:
                self._reset_connect_state()
                self.state.in_saved_networks_mode = False
                self.state.saved_networks_list    = []
                self.state.current_menu           = MENU_WIFI
                self.render()
            return None

        # ── pairing flow running ──────────────────────────────────────────────
        if self.state.pairing_active:
            if self.state.wifi_connect_result is None:
                self.render_connecting_status()
                return None
            if self.state.wifi_result_shown_at == 0.0:
                self.render_connect_result()
                return None
            if time.time() - self.state.wifi_result_shown_at >= MESSAGE_DISPLAY_S:
                self._reset_connect_state()
                self.state.pairing_active = False
                self.state.current_menu   = MENU_WIFI
                self.render()
            return None

        return None

    def _reset_connect_state(self):
        self.state.wifi_connecting      = False
        self.state.wifi_connect_status  = ""
        self.state.wifi_connect_result  = None
        self.state.wifi_result_shown_at = 0.0

    # ── network confirmation ──────────────────────────────────────────────────

    def render_network_confirmation(self):
        current_time = time.time()
        network_name = self.state.network_to_connect
        T = self._theme(); img = self.canvas(); draw = ImageDraw.Draw(img)
        self.draw_title(draw, "Connect?", title_size=17)
        draw_divider(draw, 52, T)

        fr15 = font_bold(15); max_chars = 17
        if network_name != self.state.last_selected_network:
            self.state.scroll_offset        = 0
            self.state.last_scroll_time     = current_time
            self.state.last_selected_network = network_name

        if len(network_name) > max_chars:
            disp = network_name + "  …  " + network_name[:10]
            if current_time - self.state.last_scroll_time > SCROLL_SPEED:
                self.state.scroll_offset = (
                    self.state.scroll_offset + 1) % (len(network_name) + 6)
                self.state.last_scroll_time = current_time
            net_disp = disp[self.state.scroll_offset: self.state.scroll_offset + max_chars]
        else:
            net_disp = network_name; self.state.scroll_offset = 0

        nw = draw.textlength(net_disp, font=fr15)
        draw.text(((240 - nw) // 2, 90), net_disp, font=fr15, fill=T["CYAN"])
        fr12 = font(12); hw = draw.textlength("to this network?", font=fr12)
        draw.text(((240 - hw) // 2, 112), "to this network?", font=fr12, fill=T["DIM"])
        draw_divider(draw, BTN_Y - 12, T)
        draw_buttons(draw, "Cancel", "Connect",
                     right_color=T["CYAN"], theme=T, y=BTN_Y)
        self.show(img)

    # ── saved networks ────────────────────────────────────────────────────────

    def render_saved_networks(self):
        current_time = time.time()
        if current_time - self.state.last_render_time < RENDER_THROTTLE:
            return True
        self.state.last_render_time = current_time

        if not self.state.saved_networks_list:
            self.state.saved_networks_list     = self.wifi_service.get_saved_networks()
            self.state.saved_networks_selected = 0

        if not self.state.saved_networks_list:
            self.render_message("No saved\nnetworks")
            time.sleep(MESSAGE_DISPLAY_S)
            return False

        T = self._theme(); img = self.canvas(); draw = ImageDraw.Draw(img)
        self.draw_title(draw, "Saved Networks", title_size=15)
        draw_divider(draw, 50, T)

        current    = self.wifi_service.get_current_ssid()
        fb13, fr13 = font_bold(13), font(13)
        display_n  = 4; item_h = 33; sel = self.state.saved_networks_selected
        start_idx  = max(0, sel - 1)
        end_idx    = min(len(self.state.saved_networks_list), start_idx + display_n)
        y          = 56

        sel_net = self.state.saved_networks_list[sel]
        if sel_net != self.state.last_selected_network:
            self.state.scroll_offset        = 0
            self.state.last_scroll_time     = current_time
            self.state.last_selected_network = sel_net

        for i in range(start_idx, end_idx):
            net    = self.state.saved_networks_list[i]
            is_cur = current is not None and net == current
            is_sel = i == sel
            color  = T["CYAN"] if is_sel else T["WHITE"]
            if is_sel:
                draw.rounded_rectangle([(24, y-2), (216, y+item_h-6)],
                                       radius=7, fill=T["SURFACE"])
                text = "▶ " + self._scrolling_name(net, is_cur, current_time)
            else:
                name = net[:15] if len(net) > 15 else net
                text = "  " + name + (" ✓" if is_cur else "")
            draw.text((28, y), text, font=fb13 if is_sel else fr13, fill=color)
            y += item_h

        if len(self.state.saved_networks_list) > display_n:
            draw_nav_arrows(draw, T, show_up=True, show_down=True,
                            up_y=198, down_y=208)
        fh = font(11); hw = draw.textlength("Tap to connect", font=fh)
        draw.text(((240 - hw) // 2, 212), "Tap to connect", font=fh, fill=T["DIM"])
        self.show(img)
        return True

    def _scrolling_name(self, net, is_cur, current_time):
        suffix = " ✓" if is_cur else ""; max_chars = 15
        if len(net) > max_chars:
            disp = net + "   " + net[:10]
            if current_time - self.state.last_scroll_time > SCROLL_SPEED:
                self.state.scroll_offset = (
                    self.state.scroll_offset + 1) % (len(net) + 4)
                self.state.last_scroll_time = current_time
            return disp[self.state.scroll_offset: self.state.scroll_offset + max_chars] + suffix
        self.state.scroll_offset = 0
        return net + suffix

    # ── change-WiFi guide ─────────────────────────────────────────────────────

    def _draw_change_wifi_step(self, idx):
        steps = [
            {"title": "Change WiFi",  "icon": "📶",
             "lines": ["Switches your meter", "to a new network.", "", "You need your", "new WiFi password."],
             "hint": "Swipe ▶ to continue"},
            {"title": "Step 1 / 3",   "icon": "📡",
             "lines": ["Screen connects to", "OrionSetup hotspot", "automatically.", "", "Keep phone near."],
             "hint": "◀ back   ▶ next"},
            {"title": "Step 2 / 3",   "icon": "📱",
             "lines": ["On your phone:", "", "  orion.local:3000", "", "Enter new WiFi."],
             "hint": "◀ back   ▶ next"},
            {"title": "Step 3 / 3",   "icon": "✅",
             "lines": ["Screen reconnects", "automatically.", "", "Takes ~30 sec.", "Swipe ▶ to START."],
             "hint": "◀ back   ▶ START"},
        ]
        step = steps[idx]; T = self._theme(); img = self.canvas(); draw = ImageDraw.Draw(img)
        ef = font_emoji(26); ew = draw.textlength(step["icon"], font=ef)
        draw.text(((240 - ew) // 2, 40), step["icon"], font=ef, fill=T["CYAN"])
        self.draw_title(draw, step["title"], title_size=15)
        fr13 = font(15); y = 82
        for line in step["lines"]:
            lw = draw.textlength(line, font=fr13)
            draw.text(((240 - lw) // 2, y), line, font=fr13, fill=T["WHITE"]); y += 20
        n = len(steps); sp = 16; sx = (240 - n * sp) // 2
        for d in range(n):
            cx = sx + d * sp + 6
            draw.ellipse([cx-4, 195, cx+4, 203],
                         fill=(T["CYAN"] if d == idx else T["DIM"]))
        fh = font(11); hw = draw.textlength(step["hint"], font=fh)
        draw.text(((240 - hw) // 2, 208), step["hint"], font=fh, fill=T["DIM"])
        self.show(img)

    def _handle_change_wifi_guide_gesture(self, gesture):
        step = getattr(self.state, "change_wifi_step", 0); num_steps = 4
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
                self._start_pairing()
            return None
        return None

    def _start_pairing(self):
        """
        Start pairing in background. Only sets state flags —
        main loop reads them via tick() and renders safely.
        """
        from services.network_service import NetworkService

        self.state.pairing_active       = True
        self.state.wifi_connecting      = True
        self.state.wifi_connect_status  = "Connecting to\nOrionSetup..."
        self.state.wifi_connect_result  = None
        self.state.wifi_result_shown_at = 0.0

        def _worker():
            success, msg = NetworkService(self).ensure_orion_connection()
            # Only write to state — never call render()
            self.state.wifi_connect_result = (success, msg)

        threading.Thread(target=_worker, daemon=True).start()

    # ── gesture router ────────────────────────────────────────────────────────

    def handle_gesture(self, gesture, touch_device=None):
        # Block gestures during async operations
        if self.state.wifi_connecting or self.state.pairing_active:
            return None

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
        if gesture == 0: return None
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
        """Tap Connect → starts async connect via state flags only."""
        if self.state.wifi_connecting:
            return None   # ignore gestures while connecting
        if gesture == 0: return None

        if gesture == GESTURE_LONG_PRESS:
            self.state.in_saved_networks_mode = True
            return MENU_WIFI

        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y   = touch_device.X_point, touch_device.Y_point
            action = hit_button(x, y, btn_y=BTN_Y)

            if action == "left":   # Cancel
                self.state.in_saved_networks_mode = True
                time.sleep(0.2)
                return MENU_WIFI

            if action == "right":  # Connect — async via state flags
                network = self.state.network_to_connect
                self._reset_connect_state()
                self.wifi_service.connect_to_saved_network_async(network, self.state)
                # Stay on MENU_CONFIRM_NETWORK — tick() will drive the UI
                return None

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
        """Start pairing — background thread writes state, main loop renders."""
        self._start_pairing()
        # Immediately show first status message (safe — we're on main thread)
        self.render_message(self.state.wifi_connect_status)

    def _handle_remove_wifi(self):
        current = self.wifi_service.get_current_ssid()
        if current:
            self.render_message(f"Removing\n{current}...")
            if self.wifi_service.disconnect_wifi():
                self.render_message("✅ WiFi removed")
            else:
                self.render_message("❌ Failed to\nremove",
                                     color=self._theme()["RED"])
        else:
            self.render_message("No active\nconnection")
        time.sleep(MESSAGE_DISPLAY_S)
        self.render()

    def render_qr_code(self):
        import qrcode
        T = self._theme(); url = "http://orion.local:3000"; qr = qrcode.make(url)
        img = self.canvas(); qr_r = qr.resize((140, 140)); img.paste(qr_r, (50, 30))
        draw = ImageDraw.Draw(img); f = font(13)
        uw = draw.textlength(url, font=f)
        draw.text(((240 - uw) // 2, 176), url, font=f, fill=T["CYAN"]); self.show(img)

    def render_loading_animation(self, message: str, duration: int = 3):
        import time as _t
        start = _t.time(); dots = 0
        while _t.time() - start < duration:
            self.render_message(f"{message}{'.' * (dots % 4)}"); _t.sleep(0.5); dots += 1