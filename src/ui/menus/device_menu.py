"""Device metrics menu — Dione/Orion circular design v3"""
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold,
                         draw_divider, draw_corner_hash,
                         draw_nav_arrows, draw_page_indicator)
from config.constants import *

CX = CY = 120
SAFE_W  = 160


class DeviceMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)

    def render(self):
        if not self.state.device_metrics_pages:
            self.render_message("Loading\nmetrics...")
            return

        T     = self._theme()
        img   = self.canvas()
        draw  = ImageDraw.Draw(img)
        total = len(self.state.device_metrics_pages)
        page  = self.state.current_page % total
        text  = self.state.device_metrics_pages[page]

        # Title
        self.draw_title(draw, "Device", title_size=17)
        draw_divider(draw, 52, T)

        # Page indicator pill — clearly visible
        draw_page_indicator(draw, page + 1, total, T, y=195)

        # Nav arrows — cyan colored, clearly visible
        draw_nav_arrows(draw, T, show_up=(page > 0), show_down=(page < total - 1),
                        up_y=56, down_y=208)

        # Content — split key: value BEFORE any wrapping so cyan detection
        # always works, even for long values like WiFi SSIDs
        fb = font_bold(14)
        fr = font(14)
        lh = 22

        rendered = []   # list of (key_or_None, value_str)
        if ": " in text:
            key, _, val = text.partition(": ")
            key_str = key + ": "
            kw      = int(draw.textlength(key_str, font=fb))
            # wrap only the value portion to remaining width
            val_lines = self.wrap_text(val, fr, max(60, SAFE_W - kw))
            rendered.append((key, val_lines[0] if val_lines else val))
            for extra in val_lines[1:]:
                rendered.append((None, "  " + extra))
        else:
            rendered.append((None, text))

        total_h = len(rendered) * lh
        y       = max(74, CY - total_h // 2)

        for (key, val) in rendered:
            if key is not None:
                key_str = key + ": "
                kw = draw.textlength(key_str, font=fb)
                vw = draw.textlength(val,     font=fr)
                x  = (240 - kw - vw) // 2
                draw.text((x,      y), key_str, font=fb, fill=T["CYAN"])
                draw.text((x + kw, y), val,     font=fr,  fill=T["WHITE"])
            else:
                lw = draw.textlength(val, font=fr)
                draw.text(((240 - lw) // 2, y), val, font=fr, fill=T["WHITE"])
            y += lh

        self.show(img)

    def handle_gesture(self, gesture, touch_device=None):
        if not self.state.device_metrics_pages:
            if gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
                return MENU_MAIN
            return None

        if gesture == GESTURE_UP:
            self.state.current_page = (
                self.state.current_page - 1) % len(self.state.device_metrics_pages)
            self.render()
        elif gesture == GESTURE_DOWN:
            self.state.current_page = (
                self.state.current_page + 1) % len(self.state.device_metrics_pages)
            self.render()
        elif gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
            self.state.current_page = 0
            return MENU_MAIN
        return None