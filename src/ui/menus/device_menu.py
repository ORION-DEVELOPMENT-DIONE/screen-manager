"""Device metrics menu — circular Orion design"""
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, GREEN, DIM, WHITE, SURFACE, BORDER,
                         font, font_bold, draw_title, draw_divider, CX, CY, SAFE_W)
from config.constants import *


class DeviceMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)

    def render(self):
        if not self.state.device_metrics_pages:
            self.render_message("Loading\nmetrics...")
            return

        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        total  = len(self.state.device_metrics_pages)
        page   = self.state.current_page % total
        text   = self.state.device_metrics_pages[page]

        # Title
        draw_title(draw, "Device", f"page {page + 1}/{total}", GREEN)
        draw_divider(draw, 54)

        # Content lines
        fb    = font_bold(13)
        fr    = font(13)
        lines = self.wrap_text(text, fr, SAFE_W)
        lh    = 20
        total_h = len(lines) * lh
        y       = max(62, CY - total_h // 2)

        for line in lines:
            if ": " in line:
                # key: value → bold key, normal value
                key, _, val = line.partition(": ")
                kw = draw.textlength(key + ": ", font=fb)
                vw = draw.textlength(val, font=fr)
                x  = (240 - kw - vw) // 2
                draw.text((x, y), key + ": ", font=fb, fill=GREEN)
                draw.text((x + kw, y), val, font=fr, fill=WHITE)
            else:
                lw = draw.textlength(line, font=fr)
                draw.text(((240 - lw) // 2, y), line, font=fr, fill=WHITE)
            y += lh

        # Nav arrows
        fa = font_bold(11)
        if total > 1:
            aw = draw.textlength("▲", font=fa)
            draw.text(((240 - aw) // 2, 57), "▲", font=fa, fill=DIM)
            draw.text(((240 - aw) // 2, 207), "▼", font=fa, fill=DIM)

        self.show(img)

    def handle_gesture(self, gesture, touch_device=None):
        if not self.state.device_metrics_pages:
            if gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
                return MENU_MAIN
            return None

        if gesture == GESTURE_UP:
            self.state.current_page = (self.state.current_page - 1) % len(self.state.device_metrics_pages)
            self.render()
        elif gesture == GESTURE_DOWN:
            self.state.current_page = (self.state.current_page + 1) % len(self.state.device_metrics_pages)
            self.render()
        elif gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
            self.state.current_page = 0
            return MENU_MAIN

        return None