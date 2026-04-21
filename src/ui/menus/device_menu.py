"""Device metrics menu — Dione/Orion circular design v3 (visual clarity update)

Visual improvements:
  - Larger font sizes: 14→16 for key/value text
  - Adaptive layout: key on top line, value below when combined width overflows
  - Character-level wrapping for long WiFi SSIDs (handled by renderer.wrap_text)
  - Better vertical centering in the circular safe area
  - Larger page indicator and nav arrows
"""
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold,
                         draw_divider, draw_corner_hash,
                         draw_nav_arrows, draw_page_indicator,
                         CX, CY, SAFE_W)
from config.constants import *


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
        self.draw_title(draw, "Device", title_size=18)
        draw_divider(draw, 52, T)

        # Page indicator pill — clearly visible, larger
        draw_page_indicator(draw, page + 1, total, T, y=192)

        # Nav arrows — cyan colored, clearly visible
        draw_nav_arrows(draw, T, show_up=(page > 0), show_down=(page < total - 1),
                        up_y=56, down_y=210)

        # Content — use size 16 for much better readability
        fb = font_bold(18)
        fr = font(18)
        lh = 24

        rendered = []   # list of (key_or_None, value_str)
        if ": " in text:
            key, _, val = text.partition(": ")
            key_str = key + ": "
            kw      = int(draw.textlength(key_str, font=fb))
            vw      = int(draw.textlength(val, font=fr))

            if kw + vw <= SAFE_W:
                # Fits on one line — key: value side by side
                rendered.append((key, val))
            else:
                # Key on its own line, value wrapped below
                rendered.append((key + ":", None))
                # Wrap value to full safe width since it's on its own lines
                val_lines = self.wrap_text(val, fr, SAFE_W)
                for vl in val_lines:
                    rendered.append((None, vl))
        else:
            rendered.append((None, text))

        total_h = len(rendered) * lh
        # Centre between divider (52) and page indicator area (185)
        content_zone = 185 - 60
        y = 60 + max(0, (content_zone - total_h) // 2)

        for (key, val) in rendered:
            if key is not None and val is not None:
                # key: value on same line
                key_str = key + ": "
                kw = draw.textlength(key_str, font=fb)
                vw = draw.textlength(val,     font=fr)
                x  = (240 - kw - vw) // 2
                draw.text((x,      y), key_str, font=fb, fill=T["CYAN"])
                draw.text((x + kw, y), val,     font=fr, fill=T["WHITE"])
            elif key is not None:
                # Key-only line (when value wraps below)
                kw = draw.textlength(key, font=fb)
                draw.text(((240 - kw) // 2, y), key, font=fb, fill=T["CYAN"])
            else:
                # Value-only line (continuation)
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