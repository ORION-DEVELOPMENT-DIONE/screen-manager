"""WiFi menu rendering and handling"""
import time
import logging
from PIL import ImageDraw
from ui.renderer import BaseRenderer
from config.constants import *
from config.themes import WIFI_MENU_EMOJIS


class WiFiMenu(BaseRenderer):
    def __init__(self, display, state, wifi_service):
        super().__init__(display, state)
        self.wifi_service = wifi_service
        self.options = ["Pair Devices", "Change WiFi", "Saved Networks", "Remove WiFi"]

    # ── Main menu render ──────────────────────────────────────────────────────

    def render(self):
        image  = self.get_background()
        draw   = ImageDraw.Draw(image)
        height = len(self.options) * 40
        y_start = (SCREEN_HEIGHT - height) // 2

        for i, item in enumerate(self.options):
            is_selected = (i == self.state.wifi_selected)
            color = self.get_selected_color() if is_selected else self.get_text_color()
            emoji  = WIFI_MENU_EMOJIS.get(item, "")
            draw.text((40,      y_start + i * 40), emoji, fill=color, font=self.get_emoji_font())
            draw.text((40 + 30, y_start + i * 40), item,  fill=color, font=self.get_font())

        self.display.show_image(image)
        del draw, image

    # ── Change WiFi: step-by-step guide ──────────────────────────────────────

    def render_change_wifi_guide(self):
        """Show a 4-step illustrated guide before launching the pairing flow.

        This directly addresses the user feedback that changing WiFi was
        confusing.  The user must swipe through each step before the actual
        AP-mode pairing begins.

        Steps
        -----
        1. What will happen (overview)
        2. Open the Orion app / visit orion.local
        3. Enter your new WiFi credentials
        4. Wait — screen will reconnect automatically
        """
        steps = [
            {
                "title": "Change WiFi",
                "lines": [
                    "This will switch your",
                    "Orion meter to a new",
                    "WiFi network.",
                    "",
                    "Swipe ▶ for steps",
                ],
                "icon": "📶",
            },
            {
                "title": "Step 1 of 3",
                "lines": [
                    "Screen connects to",
                    "OrionSetup hotspot",
                    "automatically.",
                    "",
                    "Keep phone nearby.",
                ],
                "icon": "📡",
            },
            {
                "title": "Step 2 of 3",
                "lines": [
                    "On your phone open:",
                    "",
                    "orion.local:3000",
                    "",
                    "Enter new WiFi info.",
                ],
                "icon": "📱",
            },
            {
                "title": "Step 3 of 3",
                "lines": [
                    "Wait for screen to",
                    "show  Connected.",
                    "",
                    "Takes ~30 seconds.",
                ],
                "icon": "⏳",
            },
        ]

        current_step = [0]   # mutable for inner scope

        def draw_step(idx):
            step  = steps[idx]
            image = self.get_background()
            draw  = ImageDraw.Draw(image)
            font_title  = self.get_font(20)
            font_body   = self.get_font(17)
            font_icon   = self.get_font(28)

            # Icon
            icon_w = font_icon.getlength(step["icon"])
            draw.text(((SCREEN_WIDTH - icon_w) // 2, 18), step["icon"],
                      fill=self.get_selected_color(), font=font_icon)

            # Title
            title_w = font_title.getlength(step["title"])
            draw.text(((SCREEN_WIDTH - title_w) // 2, 60), step["title"],
                      fill=self.get_selected_color(), font=font_title)

            # Body lines
            y = 90
            for line in step["lines"]:
                if line:
                    lw = font_body.getlength(line)
                    draw.text(((SCREEN_WIDTH - lw) // 2, y), line,
                              fill=self.get_text_color(), font=font_body)
                y += 22

            # Progress dots
            dot_total = len(steps)
            dot_spacing = 16
            dot_x_start = (SCREEN_WIDTH - dot_total * dot_spacing) // 2
            for d in range(dot_total):
                cx = dot_x_start + d * dot_spacing + 6
                cy = 215
                color = self.get_selected_color() if d == idx else "gray"
                draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=color)

            # Navigation hint
            hint = "Swipe ◀ back  ▶ next" if idx < len(steps) - 1 else "Swipe ▶ to start"
            hint_font = self.get_font(12)
            hint_w = hint_font.getlength(hint)
            draw.text(((SCREEN_WIDTH - hint_w) // 2, 228), hint,
                      fill="gray", font=hint_font)

            self.display.show_image(image)
            del draw, image

        # Interactive gesture loop for the guide
        draw_step(0)

        from config.constants import GESTURE_LEFT, GESTURE_RIGHT, GESTURE_LONG_PRESS
        # Import touch gesture codes that may differ from GESTURE_UP/DOWN
        LEFT_CODES  = {GESTURE_LEFT, 0x03}
        RIGHT_CODES = {GESTURE_RIGHT, 0x04}

        # We need the parent app's touch object — pass via state shortcut
        # The guide loop runs synchronously; returns True = proceed, False = cancel
        start_time = time.time()
        GUIDE_TIMEOUT = 120   # auto-cancel after 2 min of inactivity

        # Import touch read directly — this method is called from handle_gesture
        # so we're already in the gesture loop; we block here briefly.
        # The caller must pass touch via render context — we use a simple poll.
        while True:
            if time.time() - start_time > GUIDE_TIMEOUT:
                return False

            # Poll gesture from state (set by interrupt callback)
            # We import the global touch object via the app context
            # The simplest compatible approach: sleep briefly and check
            # This matches the existing handle_loop() pattern
            time.sleep(0.05)

            # The guide is driven by the gesture returned to handle_gesture —
            # we can't block here without breaking the loop.
            # Instead we return a special sentinel and let handle_gesture
            # drive step-by-step using state.
            # See _handle_change_wifi_guide_gesture() below.
            break

        return True   # caller will drive via gesture routing

    # ── Saved networks render ─────────────────────────────────────────────────

    def render_saved_networks(self):
        current_time = time.time()
        if current_time - self.state.last_render_time < RENDER_THROTTLE:
            return True
        self.state.last_render_time = current_time

        if not self.state.saved_networks_list:
            self.state.saved_networks_list   = self.wifi_service.get_saved_networks()
            self.state.saved_networks_selected = 0

        if not self.state.saved_networks_list:
            self.render_message("No saved\nnetworks found")
            time.sleep(2)
            return False

        image = self.get_background()
        draw  = ImageDraw.Draw(image)

        title_font = self.get_font(18)
        title      = "Saved Networks"
        title_w    = title_font.getlength(title)
        draw.text(((SCREEN_WIDTH - title_w) // 2, 30), title,
                  fill=self.get_selected_color(), font=title_font)

        current       = self.wifi_service.get_current_ssid()
        network_font  = self.get_font(20)
        display_count = 4
        item_spacing  = 32
        start_idx     = max(0, self.state.saved_networks_selected - 1)
        end_idx       = min(len(self.state.saved_networks_list), start_idx + display_count)
        y_cur         = 60
        selected_net  = self.state.saved_networks_list[self.state.saved_networks_selected]

        if selected_net != self.state.last_selected_network:
            self.state.scroll_offset       = 0
            self.state.last_scroll_time    = current_time
            self.state.last_selected_network = selected_net

        for i in range(start_idx, end_idx):
            network     = self.state.saved_networks_list[i]
            is_current  = (current is not None and network == current)
            is_selected = (i == self.state.saved_networks_selected)
            color       = self.get_selected_color() if is_selected else self.get_text_color()

            if is_selected:
                text = self._get_scrolling_text(network, is_current, current_time)
            else:
                suffix       = " ✓" if is_current else ""
                display_name = network[:17] if len(network) > 17 else network
                text         = f"  {display_name}{suffix}"

            draw.text((10, y_cur), text, fill=color, font=network_font)
            y_cur += item_spacing

        if len(self.state.saved_networks_list) > display_count:
            sf = self.get_font(14)
            sw = sf.getlength("▲▼")
            draw.text(((SCREEN_WIDTH - sw) // 2, 190), "▲▼",
                      fill=self.get_selected_color(), font=sf)

        inf = self.get_font(14)
        iw  = inf.getlength("Tap=Connect")
        draw.text(((SCREEN_WIDTH - iw) // 2, 210), "Tap=Connect",
                  fill="gray", font=inf)

        self.display.show_image(image)
        del draw, image
        return True

    def _get_scrolling_text(self, network, is_current, current_time):
        prefix    = "➤ "
        suffix    = " ✓" if is_current else ""
        max_chars = 18
        if len(network) > max_chars:
            display_network = network + "  ...  " + network[:10]
            if current_time - self.state.last_scroll_time > SCROLL_SPEED:
                self.state.scroll_offset = (self.state.scroll_offset + 1) % (len(network) + 7)
                self.state.last_scroll_time = current_time
            visible = display_network[self.state.scroll_offset:self.state.scroll_offset + max_chars]
            return prefix + visible + suffix
        self.state.scroll_offset = 0
        return prefix + network + suffix

    # ── Network confirmation render ───────────────────────────────────────────

    def render_network_confirmation(self):
        current_time = time.time()
        network_name = self.state.network_to_connect
        image = self.get_background()
        draw  = ImageDraw.Draw(image)

        msg_font = self.get_font(18)
        msg1_w   = msg_font.getlength("Connect to:")
        draw.text(((SCREEN_WIDTH - msg1_w) // 2, 30), "Connect to:",
                  fill=self.get_text_color(), font=msg_font)

        net_font  = self.get_font(18)
        max_chars = 20

        if network_name != self.state.last_selected_network:
            self.state.scroll_offset       = 0
            self.state.last_scroll_time    = current_time
            self.state.last_selected_network = network_name

        if len(network_name) > max_chars:
            display_network = network_name + "  ...  " + network_name[:10]
            if current_time - self.state.last_scroll_time > SCROLL_SPEED:
                self.state.scroll_offset = (self.state.scroll_offset + 1) % (len(network_name) + 7)
                self.state.last_scroll_time = current_time
            network_display = display_network[self.state.scroll_offset:self.state.scroll_offset + max_chars]
        else:
            network_display = network_name
            self.state.scroll_offset = 0

        net_w = net_font.getlength(network_display)
        draw.text(((SCREEN_WIDTH - net_w) // 2, 55), network_display,
                  fill=self.get_selected_color(), font=net_font)

        msg2_w = msg_font.getlength("?")
        draw.text(((SCREEN_WIDTH - msg2_w) // 2, 80), "?",
                  fill=self.get_text_color(), font=msg_font)

        self._draw_yes_no_buttons(draw)
        self.display.show_image(image)
        del draw, image

    def _draw_yes_no_buttons(self, draw):
        box_w, box_h  = 90, 50
        box_y         = 130
        spacing       = 20
        total_width   = 2 * box_w + spacing
        start_x       = (SCREEN_WIDTH - total_width) // 2

        draw.rectangle([start_x, box_y, start_x + box_w, box_y + box_h],
                       outline=self.get_text_color(), width=2)
        no_w = self.get_font().getlength("No")
        draw.text((start_x + (box_w - no_w) // 2, box_y + 12), "No",
                  fill=self.get_text_color(), font=self.get_font())

        draw.rectangle([start_x + box_w + spacing, box_y,
                        start_x + 2 * box_w + spacing, box_y + box_h],
                       outline=self.get_selected_color(), width=2)
        yes_w = self.get_font().getlength("Yes")
        draw.text((start_x + box_w + spacing + (box_w - yes_w) // 2, box_y + 12), "Yes",
                  fill=self.get_selected_color(), font=self.get_font())

    def render_qr_code(self):
        import qrcode
        url = "http://orion.local:3000"
        qr  = qrcode.make(url)
        image = self.get_background()
        qr_size   = 160
        qr_resized = qr.resize((qr_size, qr_size))
        image.paste(qr_resized, ((SCREEN_WIDTH - qr_size) // 2, 20))
        draw = ImageDraw.Draw(image)
        url_font = self.get_font(16)
        url_w    = url_font.getlength(url)
        draw.text(((SCREEN_WIDTH - url_w) // 2, 20 + qr_size + 10), url,
                  fill=self.get_selected_color(), font=url_font)
        self.display.show_image(image)
        del draw, image

    # ── Gesture handling ──────────────────────────────────────────────────────

    def handle_gesture(self, gesture, touch_device=None):
        if self.state.in_saved_networks_mode:
            return self._handle_saved_networks_gesture(gesture)
        if self.state.in_wifi_qr_mode:
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

    def _handle_change_wifi_guide_gesture(self, gesture):
        """Drive the step-by-step change-WiFi guide one swipe at a time."""
        step      = getattr(self.state, "change_wifi_step", 0)
        num_steps = 4

        if gesture in (GESTURE_LEFT, GESTURE_LONG_PRESS):
            if step > 0:
                self.state.change_wifi_step = step - 1
                self._draw_change_wifi_step(step - 1)
            else:
                # Cancel
                self.state.in_change_wifi_guide = False
                self.state.change_wifi_step     = 0
                self.render()
            return None

        if gesture in (GESTURE_RIGHT, GESTURE_TAP):
            if step < num_steps - 1:
                self.state.change_wifi_step = step + 1
                self._draw_change_wifi_step(step + 1)
            else:
                # Final step confirmed — launch pairing
                self.state.in_change_wifi_guide = False
                self.state.change_wifi_step     = 0
                self._launch_change_wifi()
            return None

        return None

    def _draw_change_wifi_step(self, idx):
        steps = [
            {
                "title": "Change WiFi",
                "icon":  "📶",
                "lines": [
                    "Switches your meter",
                    "to a new network.",
                    "",
                    "You will need your",
                    "new WiFi password.",
                ],
                "hint": "Swipe ▶ to continue",
            },
            {
                "title": "Step 1 / 3",
                "icon":  "📡",
                "lines": [
                    "Screen connects to",
                    "OrionSetup hotspot",
                    "automatically.",
                    "",
                    "Keep your phone near.",
                ],
                "hint": "◀ back   ▶ next",
            },
            {
                "title": "Step 2 / 3",
                "icon":  "📱",
                "lines": [
                    "On your phone go to:",
                    "",
                    "  orion.local:3000",
                    "",
                    "Enter new WiFi info.",
                ],
                "hint": "◀ back   ▶ next",
            },
            {
                "title": "Step 3 / 3",
                "icon":  "✅",
                "lines": [
                    "Screen reconnects",
                    "automatically.",
                    "",
                    "Takes ~30 seconds.",
                    "Swipe ▶ to start.",
                ],
                "hint": "◀ back   ▶ START",
            },
        ]

        step   = steps[idx]
        image  = self.get_background()
        draw   = ImageDraw.Draw(image)
        num_steps = len(steps)

        # Icon
        icon_font = self.get_emoji_font(30)
        icon_w    = icon_font.getlength(step["icon"])
        draw.text(((SCREEN_WIDTH - icon_w) // 2, 10), step["icon"],
                  fill=self.get_selected_color(), font=icon_font)

        # Title
        title_font = self.get_font(19)
        title_w    = title_font.getlength(step["title"])
        draw.text(((SCREEN_WIDTH - title_w) // 2, 55), step["title"],
                  fill=self.get_selected_color(), font=title_font)

        # Body
        body_font = self.get_font(16)
        y = 82
        for line in step["lines"]:
            lw = body_font.getlength(line)
            draw.text(((SCREEN_WIDTH - lw) // 2, y), line,
                      fill=self.get_text_color(), font=body_font)
            y += 21

        # Progress dots
        dot_spacing = 18
        dot_x_start = (SCREEN_WIDTH - num_steps * dot_spacing) // 2
        for d in range(num_steps):
            cx = dot_x_start + d * dot_spacing + 6
            cy = 200
            fill = self.get_selected_color() if d == idx else "gray"
            draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=fill)

        # Hint
        hint_font = self.get_font(11)
        hint_w    = hint_font.getlength(step["hint"])
        draw.text(((SCREEN_WIDTH - hint_w) // 2, 213), step["hint"],
                  fill="gray", font=hint_font)

        self.display.show_image(image)
        del draw, image

    def _launch_change_wifi(self):
        from services.network_service import NetworkService
        self.render_message("Connecting to\nOrionSetup...")
        self.render_loading_animation("Switching", 8)
        network_service = NetworkService(self)
        success, message = network_service.ensure_orion_connection()
        self.render_message(message)
        time.sleep(2)
        self.render()

    def _handle_saved_networks_gesture(self, gesture):
        if gesture == 0:
            return None
        elif gesture == GESTURE_UP:
            self.state.saved_networks_selected = \
                (self.state.saved_networks_selected - 1) % len(self.state.saved_networks_list)
            self.render_saved_networks()
        elif gesture == GESTURE_DOWN:
            self.state.saved_networks_selected = \
                (self.state.saved_networks_selected + 1) % len(self.state.saved_networks_list)
            self.render_saved_networks()
        elif gesture == GESTURE_TAP:
            self.state.network_to_connect       = self.state.saved_networks_list[self.state.saved_networks_selected]
            self.state.in_saved_networks_mode   = False
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

    def _handle_wifi_selection(self):
        time.sleep(0.1)
        if self.state.wifi_selected == 0:    # Pair Devices
            self._handle_pair_devices()
        elif self.state.wifi_selected == 1:  # Change WiFi — show guide first
            self.state.in_change_wifi_guide = True
            self.state.change_wifi_step     = 0
            self._draw_change_wifi_step(0)
        elif self.state.wifi_selected == 2:  # Saved Networks
            self.state.in_saved_networks_mode  = True
            self.state.saved_networks_list     = self.wifi_service.get_saved_networks()
            self.state.saved_networks_selected = 0
            if not self.render_saved_networks():
                self.state.in_saved_networks_mode = False
            time.sleep(0.2)
        elif self.state.wifi_selected == 3:  # Remove WiFi
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

    def render_loading_animation(self, message, duration=3):
        start = time.time()
        dots  = 0
        while time.time() - start < duration:
            self.render_message(f"{message}{'.' * (dots % 4)}")
            time.sleep(0.5)
            dots += 1

    def handle_confirmation_gesture(self, gesture, touch_device):
        if gesture == 0:
            return None
        if gesture == GESTURE_LONG_PRESS:
            self.state.in_saved_networks_mode = True
            return MENU_WIFI
        if gesture == GESTURE_TAP:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            box_w, box_h = 90, 50
            box_y        = 130
            spacing      = 20
            start_x      = (SCREEN_WIDTH - (2 * box_w + spacing)) // 2

            if start_x <= x <= start_x + box_w and box_y <= y <= box_y + box_h:
                self.state.in_saved_networks_mode = True
                time.sleep(0.2)
                return MENU_WIFI

            if (start_x + box_w + spacing <= x <= start_x + 2 * box_w + spacing
                    and box_y <= y <= box_y + box_h):
                if self.wifi_service.connect_to_saved_network(self.state.network_to_connect):
                    self.render_message("✅ Connected")
                else:
                    self.render_message("❌ Failed")
                time.sleep(2)
                self.state.in_saved_networks_mode = False
                self.state.saved_networks_list    = []
                return MENU_WIFI
        return None