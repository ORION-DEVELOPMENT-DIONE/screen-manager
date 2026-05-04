"""Pairing screen renderer — QR code + step-by-step progress indicators

Renders on the 240x240 round LCD during ESP32 pairing flow:
  - Step 0: Initializing   — spinner animation
  - Step 1: Scanning        — scanning animation
  - Step 2: Portal active   — QR code + instructions
  - Step 3: Connecting      — connecting to new WiFi
  - Step 4: Done            — success or error

Thread-safe: only called from main loop via tick().
"""
import logging
import time

try:
    import qrcode
except ImportError:
    qrcode = None

from PIL import Image, ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold, font_emoji,
                         draw_divider, CX, CY, SAFE_W)

log = logging.getLogger("orion.pairing")

# ── Portal URL for QR code ────────────────────────────────────────────────────
PORTAL_URL = "http://192.168.4.1"

# ── QR code cache ─────────────────────────────────────────────────────────────
_qr_cache = None


def _generate_qr(url, box_size=2, border=1):
    """Generate QR code image for portal URL. Cached after first call."""
    global _qr_cache
    if _qr_cache is not None:
        return _qr_cache.copy()

    if qrcode is None:
        log.warning("qrcode module not installed")
        placeholder = Image.new("RGB", (60, 60), (255, 255, 255))
        draw = ImageDraw.Draw(placeholder)
        draw.text((8, 22), "QR N/A", fill=(0, 0, 0))
        return placeholder

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    _qr_cache = img.copy()
    log.info("QR code generated for %s (%dx%d)", url, img.width, img.height)
    return img.copy()


def invalidate_qr_cache():
    """Clear cached QR image."""
    global _qr_cache
    _qr_cache = None


class PairingScreenRenderer:
    """Renders pairing step-by-step screens on the round LCD."""

    def __init__(self, base_renderer):
        self.br = base_renderer
        self._last_step = -1
        self._anim_frame = 0

    def render(self):
        """Render current pairing step based on state.pairing_step."""
        step = getattr(self.br.state, 'pairing_step', -1)

        if step != self._last_step:
            log.info("Pairing screen -> step %d", step)
            self._last_step = step

        if step == 0:
            self._render_initializing()
        elif step == 1:
            self._render_scanning()
        elif step == 2:
            self._render_portal()
        elif step == 3:
            self._render_connecting()
        elif step == 4:
            self._render_done()
        else:
            self.br.render_message(
                self.br.state.wifi_connect_status or "Pairing..."
            )

    # ── Step 0: Initializing ──────────────────────────────────────────────────

    def _render_initializing(self):
        T = self.br._theme()
        img = self.br.canvas()
        draw = ImageDraw.Draw(img)

        self.br.draw_title(draw, "Pairing", title_size=17)
        draw_divider(draw, 48, T)
        self._draw_step_bar(draw, T, current_step=0)

        self._anim_frame = (self._anim_frame + 1) % 8
        fb = font_bold(15)
        label = getattr(self.br.state, 'pairing_step_label', 'Initializing')
        dots = "." * ((self._anim_frame // 2) % 4)
        text = f"{label}{dots}"
        tw = draw.textlength(text, font=fb)
        draw.text(((240 - tw) // 2, CY + 10), text, font=fb, fill=T["CYAN"])

        fh = font(11)
        hint = "Please wait..."
        hw = draw.textlength(hint, font=fh)
        draw.text(((240 - hw) // 2, 205), hint, font=fh, fill=T["DIM"])

        self.br.show(img)

    # ── Step 1: Scanning ──────────────────────────────────────────────────────

    def _render_scanning(self):
        T = self.br._theme()
        img = self.br.canvas()
        draw = ImageDraw.Draw(img)

        self.br.draw_title(draw, "Scanning", title_size=17)
        draw_divider(draw, 48, T)
        self._draw_step_bar(draw, T, current_step=1)

        # Animated arcs — centered vertically below step bar
        self._anim_frame = (self._anim_frame + 1) % 12
        arc_count = (self._anim_frame // 3) % 4
        arc_cy = CY + 15
        for i in range(arc_count + 1):
            r = 18 + i * 10
            bbox = [CX - r, arc_cy - r, CX + r, arc_cy + r]
            draw.arc(bbox, start=200, end=340, fill=T["CYAN"], width=2)

        draw.ellipse([CX - 3, arc_cy - 3, CX + 3, arc_cy + 3], fill=T["CYAN"])

        fb = font_bold(14)
        label = getattr(self.br.state, 'pairing_step_label', 'Scanning')
        tw = draw.textlength(label, font=fb)
        draw.text(((240 - tw) // 2, CY + 55), label, font=fb, fill=T["WHITE"])

        fr = font(12)
        status = self.br.state.wifi_connect_status or ""
        if status:
            lines = status.split("\n")
            y = CY + 75
            for line in lines[:2]:
                lw = draw.textlength(line, font=fr)
                draw.text(((240 - lw) // 2, y), line, font=fr, fill=T["DIM"])
                y += 16

        self.br.show(img)

    # ── Step 2: Portal active — QR code ───────────────────────────────────────

    def _render_portal(self):
        T = self.br._theme()
        img = self.br.canvas()
        draw = ImageDraw.Draw(img)

        # Title — smaller, higher
        self.br.draw_title(draw, "Setup WiFi", title_size=17)
        draw_divider(draw, 48, T)
        self._draw_step_bar(draw, T, current_step=2)

        # QR code — larger, starts below step bar labels
        qr_img = _generate_qr(PORTAL_URL, box_size=3, border=1)
        qr_size = min(qr_img.width, qr_img.height, 150)
        qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)

        qr_x = CX - qr_size // 2
        qr_y = 85
        border_px = 3
        draw.rounded_rectangle(
            [(qr_x - border_px, qr_y - border_px),
             (qr_x + qr_size + border_px, qr_y + qr_size + border_px)],
            radius=3, fill=(255, 255, 255)
        )
        img.paste(qr_img, (qr_x, qr_y))

        # Instructions at bottom — no URL, no "Waiting" text
        y = qr_y + qr_size + border_px + 8
        fr_hint = font(11)
        hints = [
            "1. Connect to OrionSetup",
            "2. Choose new WiFi",
            "3. Enter password",
        ]
        for hint in hints:
            hw = draw.textlength(hint, font=fr_hint)
            draw.text(((240 - hw) // 2, y), hint, font=fr_hint, fill=T["DIM"])
            y += 15

        self.br.show(img)

    # ── Step 3: Connecting to new WiFi ────────────────────────────────────────

    def _render_connecting(self):
        T = self.br._theme()
        img = self.br.canvas()
        draw = ImageDraw.Draw(img)

        self.br.draw_title(draw, "Connecting", title_size=17)
        draw_divider(draw, 48, T)
        self._draw_step_bar(draw, T, current_step=3)

        ssid = getattr(self.br.state, 'pairing_ssid', '') or ''
        fb = font_bold(16)
        if ssid:
            display_ssid = ssid if len(ssid) <= 18 else ssid[:16] + ".."
            sw = draw.textlength(display_ssid, font=fb)
            draw.text(((240 - sw) // 2, CY - 10), display_ssid, font=fb, fill=T["CYAN"])

        self._anim_frame = (self._anim_frame + 1) % 12
        fr = font(13)
        n_dots = (self._anim_frame // 3) % 4 + 1
        dots = "●" * n_dots + "○" * (4 - n_dots)
        dw = draw.textlength(dots, font=fr)
        draw.text(((240 - dw) // 2, CY + 16), dots, font=fr, fill=T["DIM"])

        status = self.br.state.wifi_connect_status or ""
        if status:
            fr_s = font(12)
            lines = status.split("\n")
            y = CY + 40
            for line in lines[:2]:
                lw = draw.textlength(line, font=fr_s)
                draw.text(((240 - lw) // 2, y), line, font=fr_s, fill=T["DIM"])
                y += 16

        fh = font(11)
        hint = "Do not disconnect..."
        hw = draw.textlength(hint, font=fh)
        draw.text(((240 - hw) // 2, 205), hint, font=fh, fill=T["DIM"])

        self.br.show(img)

    # ── Step 4: Done (success or error) ───────────────────────────────────────

    def _render_done(self):
        T = self.br._theme()
        img = self.br.canvas()
        draw = ImageDraw.Draw(img)

        error = getattr(self.br.state, 'pairing_error', '')
        success = not error

        if success:
            self.br.draw_title(draw, "Complete!", title_size=17)
            draw_divider(draw, 48, T)
            self._draw_step_bar(draw, T, current_step=4)

            fb = font_bold(28)
            check = "✓"
            cw = draw.textlength(check, font=fb)
            draw.text(((240 - cw) // 2, CY - 20), check, font=fb, fill=T["CYAN"])

            ssid = getattr(self.br.state, 'pairing_ssid', '') or ''
            if ssid:
                fr = font_bold(14)
                display = ssid if len(ssid) <= 18 else ssid[:16] + ".."
                sw = draw.textlength(display, font=fr)
                draw.text(((240 - sw) // 2, CY + 20), display, font=fr, fill=T["WHITE"])

            fh = font(11)
            hint = "Pairing successful"
            hw = draw.textlength(hint, font=fh)
            draw.text(((240 - hw) // 2, 205), hint, font=fh, fill=T["CYAN"])
        else:
            self.br.draw_title(draw, "Error", title_size=17)
            draw_divider(draw, 48, T)
            self._draw_step_bar(draw, T, current_step=4, error=True)

            fb = font_bold(28)
            x_mark = "✗"
            xw = draw.textlength(x_mark, font=fb)
            draw.text(((240 - xw) // 2, CY - 20), x_mark, font=fb, fill=T["RED"])

            fr = font(13)
            lines = error.split("\n")
            y = CY + 18
            for line in lines[:3]:
                lw = draw.textlength(line, font=fr)
                draw.text(((240 - lw) // 2, y), line, font=fr, fill=T["WHITE"])
                y += 18

            fh = font(11)
            hint = "Long press -> back"
            hw = draw.textlength(hint, font=fh)
            draw.text(((240 - hw) // 2, 205), hint, font=fh, fill=T["DIM"])

        self.br.show(img)

    # ── Step progress bar ─────────────────────────────────────────────────────

    def _draw_step_bar(self, draw, T, current_step, y=55, error=False):
        """Draw horizontal step progress: ●───●───●───○───○"""
        n = 5
        spacing = 30
        total_w = (n - 1) * spacing
        x_start = CX - total_w // 2

        for i in range(n):
            x = x_start + i * spacing

            # Line to previous dot
            if i > 0:
                px = x_start + (i - 1) * spacing
                line_color = T["CYAN"] if i <= current_step else T["DIM"]
                if error and i == n - 1:
                    line_color = T["RED"]
                draw.line([(px + 4, y), (x - 4, y)], fill=line_color, width=2)

            # Dot
            r = 4 if i == current_step else 3
            if i < current_step:
                draw.ellipse([x - r, y - r, x + r, y + r], fill=T["CYAN"])
            elif i == current_step:
                color = T["RED"] if (error and i == n - 1) else T["CYAN"]
                draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
                draw.ellipse([x - r - 2, y - r - 2, x + r + 2, y + r + 2],
                            outline=color, width=1)
            else:
                draw.ellipse([x - r, y - r, x + r, y + r],
                            outline=T["DIM"], width=1)

        # Step labels
        fl = font(10)
        labels = ["Init", "Scan", "Setup", "Join", "Done"]
        for i, lbl in enumerate(labels):
            x = x_start + i * spacing
            lw = draw.textlength(lbl, font=fl)
            color = T["CYAN"] if i <= current_step else T["DIM"]
            if error and i == n - 1:
                color = T["RED"]
            draw.text((x - lw // 2, y + 7), lbl, font=fl, fill=color)