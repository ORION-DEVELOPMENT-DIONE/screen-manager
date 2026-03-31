"""
Update Menu — Orion Screen Manager
Dione Protocol visual identity: deep-space dark + electric blue + solar amber
Round-screen safe: all content kept within 200px diameter circle
"""

import time
import math
import threading
from PIL import Image, ImageDraw, ImageFont
from ui.renderer import BaseRenderer
from config.constants import *

# ── Dione Protocol colour palette ─────────────────────────────────────────────
_BG       = (5,   11,  24)    # deep space
_SURFACE  = (10,  20,  42)    # card surface
_RING     = (0,   80,  160)   # outer ring
_BLUE     = (0,   163, 255)   # electric blue — primary accent
_CYAN     = (0,   220, 200)   # teal-cyan — secondary accent
_AMBER    = (245, 158, 11)    # solar amber — update/warning
_TEXT     = (210, 230, 255)   # cool white
_DIM      = (80,  100, 130)   # muted
_DIVIDER  = (20,  40,  70)

# ── layout (240×240 round display) ────────────────────────────────────────────
W, H          = 240, 240
CX, CY        = 120, 120
R             = 118

SAFE_TOP      = 28
SAFE_BOT      = 212
SAFE_L        = 24
SAFE_R        = 216
SAFE_W        = SAFE_R - SAFE_L   # 192

TITLE_TOP     = SAFE_TOP          # 28
TITLE_BOT     = 68
SCROLL_TOP    = TITLE_BOT + 4     # 72
SCROLL_BOT    = 168
SCROLL_VIS_H  = SCROLL_BOT - SCROLL_TOP   # 96
BTN_TOP       = 174
BTN_BOT       = SAFE_BOT          # 212

SCROLL_SPEED  = 1
SCROLL_DELAY  = 0.04
PAUSE_TOP     = 1.5
PAUSE_BOT     = 2.0


# ── fonts ─────────────────────────────────────────────────────────────────────

def _font(size):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "../Font/DejaVuSans.ttf",
    ]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _font_bold(size):
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "../Font/DejaVuSans.ttf",
    ]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(text, font, max_w, draw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ── circle mask ───────────────────────────────────────────────────────────────

def _make_circle_mask():
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse(
        [(CX - R, CY - R), (CX + R, CY + R)], fill=255
    )
    return mask


_CIRCLE_MASK = _make_circle_mask()


def _apply_circle_mask(img):
    out = Image.new("RGB", (W, H), (0, 0, 0))
    out.paste(img, mask=_CIRCLE_MASK)
    return out


# ── base frame ────────────────────────────────────────────────────────────────

def _make_base_frame():
    img  = Image.new("RGB", (W, H), _BG)
    draw = ImageDraw.Draw(img)

    # Faint star field
    import random
    rng = random.Random(7)
    for _ in range(55):
        sx, sy = rng.randint(8, 232), rng.randint(8, 232)
        if math.hypot(sx - CX, sy - CY) < R - 4:
            v = rng.randint(25, 70)
            draw.point((sx, sy), fill=(v, v + 15, v + 30))

    # Outer glow ring
    draw.ellipse([(CX - R + 1, CY - R + 1), (CX + R - 1, CY + R - 1)],
                 outline=_RING, width=2)
    # Subtle inner circle at scroll boundary
    draw.ellipse([(CX - 94, CY - 94), (CX + 94, CY + 94)],
                 outline=_DIVIDER, width=1)

    return img


# ── description canvas ────────────────────────────────────────────────────────

def _build_desc_canvas(description):
    f_hdr  = _font_bold(12)
    f_body = _font(11)

    scratch = Image.new("RGB", (SAFE_W, 2000), _BG)
    d = ImageDraw.Draw(scratch)
    y = 6
    items = []

    for raw in description.splitlines():
        line = raw.strip()
        if not line:
            y += 5
            continue
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            items.append(("hdr", text, f_hdr, _CYAN, 0, y))
            y += 14 + 3
        else:
            for wl in _wrap(line, f_body, SAFE_W - 6, d):
                items.append(("body", wl, f_body, _TEXT, 2, y))
                y += 12 + 3
        y += 1

    content_h = max(y + 10, SCROLL_VIS_H)
    canvas = Image.new("RGB", (SAFE_W, content_h), _BG)
    draw   = ImageDraw.Draw(canvas)

    for (kind, text, font, color, x, ry) in items:
        if kind == "hdr":
            tw = int(draw.textlength(text, font=font)) + 10
            draw.rounded_rectangle(
                [(x - 2, ry - 1), (x + tw, ry + 13)],
                radius=3, fill=(0, 38, 52)
            )
            draw.line([(x - 2, ry + 14), (min(x + tw, SAFE_W - 2), ry + 14)],
                      fill=_CYAN, width=1)
        draw.text((x, ry), text, font=font, fill=color)

    return canvas, content_h


# ── UpdateMenu ────────────────────────────────────────────────────────────────

class UpdateMenu(BaseRenderer):

    def __init__(self, display, state, update_checker):
        super().__init__(display, state)
        self.update_checker  = update_checker
        self._scroll_offset  = 0
        self._scroll_running = False
        self._scroll_thread  = None
        self._desc_canvas    = None
        self._desc_h         = 0
        self._base_frame     = None
        self._cached_info    = None
        self._btn_left_rect  = None
        self._btn_right_rect = None

    # ── drawing helpers ───────────────────────────────────────────────────────

    def _get_base(self):
        if self._base_frame is None:
            self._base_frame = _make_base_frame()
        return self._base_frame.copy()

    def _draw_title(self, draw, info):
        available = info['available']
        accent    = _AMBER if available else _BLUE
        title     = "Update Available" if available else "Up to Date"
        f_t = _font_bold(14)
        f_v = _font(10)

        # Accent underline
        draw.line([(SAFE_L, TITLE_BOT - 1), (SAFE_R, TITLE_BOT - 1)],
                  fill=accent, width=1)

        tw = draw.textlength(title, font=f_t)
        draw.text(((W - tw) // 2, TITLE_TOP + 2), title, font=f_t, fill=accent)

        cur = info['current']
        lat = info.get('latest', cur)
        vtxt = f"{cur}  →  {lat}" if (available and lat != cur) else f"v {cur}"
        vw = draw.textlength(vtxt, font=f_v)
        draw.text(((W - vw) // 2, TITLE_TOP + 20), vtxt, font=f_v, fill=_DIM)

    def _paste_scroll(self, frame, info):
        if self._desc_canvas is None:
            draw = ImageDraw.Draw(frame)
            f = _font_bold(11)
            msg = "No description available"
            mw = draw.textlength(msg, font=f)
            mid_y = (SCROLL_TOP + SCROLL_BOT) // 2 - 6
            draw.text(((W - mw) // 2, mid_y), msg, font=f, fill=_DIM)
            return

        offset = self._scroll_offset
        end    = offset + SCROLL_VIS_H

        if end <= self._desc_h:
            crop = self._desc_canvas.crop((0, offset, SAFE_W, end))
        else:
            bot_h = self._desc_h - offset
            crop  = Image.new("RGB", (SAFE_W, SCROLL_VIS_H), _BG)
            if bot_h > 0:
                crop.paste(
                    self._desc_canvas.crop((0, offset, SAFE_W, offset + bot_h)),
                    (0, 0)
                )
            top_h = SCROLL_VIS_H - bot_h
            if top_h > 0:
                crop.paste(
                    self._desc_canvas.crop((0, 0, SAFE_W, top_h)),
                    (0, bot_h)
                )

        frame.paste(crop, (SAFE_L, SCROLL_TOP))

    def _draw_fade_edges(self, draw):
        """Soft fade at top/bottom of scroll zone."""
        fade = 10
        for i in range(fade):
            a = int(180 * (1 - i / fade))
            r, g, b = _BG
            c = (max(0, r - a // 3), max(0, g - a // 3), max(0, b - a // 3))
            draw.line([(SAFE_L, SCROLL_TOP + i), (SAFE_R, SCROLL_TOP + i)], fill=c)
            draw.line([(SAFE_L, SCROLL_BOT - 1 - i), (SAFE_R, SCROLL_BOT - 1 - i)], fill=c)

    def _draw_buttons(self, draw, info):
        available = info['available']
        f  = _font_bold(12)
        bw = 82
        bh = 28
        gap = 8
        total = 2 * bw + gap
        sx = (W - total) // 2
        rx = sx + bw + gap
        by = BTN_TOP + (BTN_BOT - BTN_TOP - bh) // 2

        if available:
            l_lbl, r_lbl = "Later",  "Update"
            l_col, r_col = _DIM,     _AMBER
            r_fill       = (48, 28,  0)
        else:
            l_lbl, r_lbl = "Back",   "Check"
            l_col, r_col = _DIM,     _BLUE
            r_fill       = (0,  22,  48)

        draw.rounded_rectangle([(sx, by), (sx + bw, by + bh)],
                                radius=7, outline=l_col, width=1)
        lw = draw.textlength(l_lbl, font=f)
        draw.text((sx + (bw - lw) // 2, by + (bh - 12) // 2),
                  l_lbl, font=f, fill=l_col)

        draw.rounded_rectangle([(rx, by), (rx + bw, by + bh)],
                                radius=7, fill=r_fill, outline=r_col, width=1)
        rw = draw.textlength(r_lbl, font=f)
        draw.text((rx + (bw - rw) // 2, by + (bh - 12) // 2),
                  r_lbl, font=f, fill=r_col)

        self._btn_left_rect  = (sx,      by, sx + bw,      by + bh)
        self._btn_right_rect = (rx,      by, rx + bw,      by + bh)

    def _draw_scroll_pip(self, draw):
        if self._desc_h <= SCROLL_VIS_H or self._desc_canvas is None:
            return
        travel   = max(1, self._desc_h - SCROLL_VIS_H)
        progress = self._scroll_offset / travel
        bar_h    = SCROLL_BOT - SCROLL_TOP - 6
        dot_y    = SCROLL_TOP + 3 + int(progress * bar_h)
        draw.ellipse([(W - 9, dot_y), (W - 5, dot_y + 5)], fill=_BLUE)

    # ── compose ───────────────────────────────────────────────────────────────

    def _compose(self, info):
        frame = self._get_base()

        # Paste scroll content first (before draw calls on top)
        self._paste_scroll(frame, info)

        draw = ImageDraw.Draw(frame)
        self._draw_title(draw, info)
        self._draw_fade_edges(draw)
        self._draw_buttons(draw, info)
        self._draw_scroll_pip(draw)

        return _apply_circle_mask(frame)

    # ── public render ─────────────────────────────────────────────────────────

    def render(self):
        info = self.update_checker.get_update_info()
        self._cached_info = info

        # Build description canvas on first render if update available
        if info['available'] and self._desc_canvas is None:
            desc = info.get('description', '')
            if desc:
                self._desc_canvas, self._desc_h = _build_desc_canvas(desc)
                self._scroll_offset = 0

        self.display.show_image(self._compose(info))

        if info['available'] and self._desc_canvas and not self._scroll_running:
            self._start_scroll(info)

    # ── scroll thread ─────────────────────────────────────────────────────────

    def _start_scroll(self, info):
        self._scroll_running = True
        self._scroll_thread  = threading.Thread(
            target=self._scroll_loop, args=(info,), daemon=True
        )
        self._scroll_thread.start()

    def _stop_scroll(self):
        self._scroll_running = False

    def _scroll_loop(self, info):
        time.sleep(PAUSE_TOP)
        max_offset = max(0, self._desc_h - SCROLL_VIS_H)

        while self._scroll_running:
            self._scroll_offset = min(self._scroll_offset + SCROLL_SPEED, max_offset)

            try:
                self.display.show_image(self._compose(info))
            except Exception as e:
                import logging
                logging.error(f"Scroll render error: {e}")
                break

            if self._scroll_offset >= max_offset:
                time.sleep(PAUSE_BOT)
                self._scroll_offset = 0
                time.sleep(PAUSE_TOP)

            time.sleep(SCROLL_DELAY)

    # ── gesture ───────────────────────────────────────────────────────────────

    def handle_gesture(self, gesture, touch_device=None):
        info = self._cached_info or self.update_checker.get_update_info()

        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            action = self._hit_button(x, y)

            if not info['available']:
                if action == "right":
                    self._stop_scroll()
                    self.render_message("Checking...")
                    self.update_checker.check_for_updates()
                    self._desc_canvas = None
                    self._base_frame  = None
                    self.render()
                    return None
                if action == "left":
                    self._stop_scroll()
                    return MENU_MAIN
            else:
                if action == "right":
                    self._stop_scroll()
                    self._perform_update()
                    return MENU_MAIN
                if action == "left":
                    self._stop_scroll()
                    return MENU_MAIN

        elif gesture in (GESTURE_LEFT, GESTURE_LONG_PRESS):
            self._stop_scroll()
            return MENU_MAIN

        return None

    def _hit_button(self, x, y):
        if self._btn_left_rect:
            x1, y1, x2, y2 = self._btn_left_rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                return "left"
        if self._btn_right_rect:
            x1, y1, x2, y2 = self._btn_right_rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                return "right"
        return None

    # ── update ────────────────────────────────────────────────────────────────

    def _perform_update(self):
        self.render_message("Updating...\nPlease wait")
        time.sleep(1)
        self._desc_canvas  = None
        self._base_frame   = None
        success, message   = self.update_checker.perform_update()
        if success:
            self.render_message("Update complete!\nRestarting...")
        else:
            self.render_message(f"Update failed\n{message}")
        time.sleep(3)
        if success:
            import os
            os.system("sudo systemctl restart screen.service")