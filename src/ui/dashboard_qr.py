"""Dashboard QR code screen — shows access URL on round LCD."""

import logging
import socket
from pathlib import Path

try:
    import qrcode
except ImportError:
    qrcode = None

from PIL import Image, ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold,
                         draw_divider, CX, CY, SAFE_W)

log = logging.getLogger("orion.dashboard_qr")

DASHBOARD_TOKEN_FILE = "/etc/orion/dashboard.token"
DASHBOARD_PORT = 3001
_qr_cache = None


def _get_dashboard_url():
    """Build dashboard access URL."""
    try:
        token = Path(DASHBOARD_TOKEN_FILE).read_text().strip()
    except Exception:
        token = ""
    hostname = socket.gethostname()
    return f"http://{hostname}.local:{DASHBOARD_PORT}/?t={token}"


def _generate_qr(url, box_size=3, border=1):
    global _qr_cache
    if _qr_cache is not None:
        return _qr_cache.copy()
    if qrcode is None:
        placeholder = Image.new("RGB", (80, 80), (255, 255, 255))
        ImageDraw.Draw(placeholder).text((8, 30), "QR N/A", fill=(0, 0, 0))
        return placeholder
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size, border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    _qr_cache = img.copy()
    log.info("Dashboard QR generated for %s (%dx%d)", url, img.width, img.height)
    return img.copy()


def invalidate_cache():
    global _qr_cache
    _qr_cache = None


class DashboardQRScreen(BaseRenderer):
    """Shows QR code for dashboard access on the round LCD."""

    def __init__(self, display, state):
        super().__init__(display, state)
    def render(self):
        T = self._theme()
        img = self.canvas()
        draw = ImageDraw.Draw(img)

        # Title — compact
        self.draw_title(draw, "Dashboard", title_size=18)
        draw_divider(draw, 52, T)

        # QR code — as large as possible
        url = _get_dashboard_url()
        qr_img = _generate_qr(url, box_size=3, border=1)
        qr_size = min(qr_img.width, qr_img.height, 160)
        qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)

        qr_x = CX - qr_size // 2
        qr_y = 65
        border_px = 5
        draw.rounded_rectangle(
            [(qr_x - border_px, qr_y - border_px),
             (qr_x + qr_size + border_px, qr_y + qr_size + border_px)],
            radius=5, fill=(255, 255, 255)
        )
        img.paste(qr_img, (qr_x, qr_y))

        # Single line instruction
        y = qr_y + qr_size + border_px + 6
        f_hint = font(11)
        hints = ["Scan to open dashboard", "on your phone or PC"]
        for hint in hints:        
            hw = draw.textlength(hint, font=f_hint)
            draw.text(((240 - hw) // 2, y),
                    hint, font=f_hint, fill=T["DIM"])
            y += 14
        self.show(img)

    def handle_gesture(self, gesture, touch_device=None):
        from config.constants import GESTURE_LEFT, GESTURE_LONG_PRESS, MENU_MAIN
        if gesture in (GESTURE_LEFT, GESTURE_LONG_PRESS):
            return MENU_MAIN
        return None