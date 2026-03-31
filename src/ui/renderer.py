"""Base rendering — circular canvas, unified Orion design system"""
from PIL import Image, ImageDraw, ImageFont
from config.constants import *

# ── Design tokens ─────────────────────────────────────────────────────────────
BG        = (10,  10,  20)       # deep navy background
SURFACE   = (18,  18,  35)       # card / bar surface
BORDER    = (30,  30,  55)       # subtle divider
GREEN     = (0,   200, 120)      # Orion accent green
ORANGE    = (255, 165, 0)        # alert / update orange
DIM       = (100, 100, 120)      # secondary text
WHITE     = (220, 220, 230)      # primary text
RED       = (220,  60,  60)      # error / danger

# Safe circle: content must stay inside r=100 centred at (120,120)
CX, CY, R = 120, 120, 100       # circle centre and radius
SAFE_W    = 170                  # safe text width (chord at mid-height)

# Font paths
_FONT_REG  = "../Font/DejaVuSans.ttf"
_FONT_BOLD = "../Font/DejaVuSans-Bold.ttf"
_FONT_EMO  = "../Font/Symbola.ttf"


def _try_font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def font(size=16):
    return _try_font([_FONT_REG,  "../Font/DejaVuSans.ttf"], size)

def font_bold(size=16):
    return _try_font([_FONT_BOLD, _FONT_REG], size)

def font_emoji(size=16):
    return _try_font([_FONT_EMO,  _FONT_REG], size)


def make_canvas() -> Image.Image:
    """Return a fresh 240×240 dark canvas with circular clip mask applied."""
    img  = Image.new("RGB", (240, 240), BG)
    mask = Image.new("L",   (240, 240), 0)
    md   = ImageDraw.Draw(mask)
    md.ellipse([CX - R, CY - R, CX + R, CY + R], fill=255)
    # Apply mask — pixels outside circle stay BG
    bg   = Image.new("RGB", (240, 240), BG)
    bg.paste(img, mask=mask)
    return bg


def draw_title(draw, title: str, subtitle: str = "", color=GREEN,
               title_size=17, sub_size=11):
    """Standard title bar: coloured title + optional grey subtitle."""
    tf = font_bold(title_size)
    tw = draw.textlength(title, font=tf)
    draw.text(((240 - tw) // 2, 28), title, font=tf, fill=color)
    if subtitle:
        sf = font(sub_size)
        sw = draw.textlength(subtitle, font=sf)
        draw.text(((240 - sw) // 2, 28 + title_size + 3), subtitle,
                  font=sf, fill=DIM)


def draw_divider(draw, y: int, color=BORDER):
    r = 80
    draw.line([(CX - r, y), (CX + r, y)], fill=color, width=1)


def draw_buttons(draw, left_label: str, right_label: str,
                 right_color=GREEN, y: int = 183):
    """Two pill buttons at the bottom of the circle."""
    bw, bh   = 88, 34
    gap      = 8
    total    = 2 * bw + gap
    sx       = (240 - total) // 2
    rx       = sx + bw + gap
    f        = font_bold(13)

    # Left — dim outline
    draw.rounded_rectangle([(sx, y), (sx + bw, y + bh)],
                            radius=8, outline=DIM, width=2)
    lw = draw.textlength(left_label, font=f)
    draw.text((sx + (bw - lw) // 2, y + (bh - 13) // 2),
              left_label, font=f, fill=DIM)

    # Right — accent outline
    draw.rounded_rectangle([(rx, y), (rx + bw, y + bh)],
                            radius=8, outline=right_color, width=2)
    rw = draw.textlength(right_label, font=f)
    draw.text((rx + (bw - rw) // 2, y + (bh - 13) // 2),
              right_label, font=f, fill=right_color)


def hit_button(x, y, btn_y=183, bw=88, bh=34, gap=8):
    """Returns 'left', 'right', or None."""
    total = 2 * bw + gap
    sx    = (240 - total) // 2
    rx    = sx + bw + gap
    if btn_y <= y <= btn_y + bh:
        if sx <= x <= sx + bw:
            return "left"
        if rx <= x <= rx + bw:
            return "right"
    return None


def draw_status_dots(draw, wifi_ok: bool, meter_ok: bool):
    """WiFi + meter status icons near top of circle."""
    ef = font_emoji(18)
    wifi_color  = GREEN if wifi_ok  else RED
    meter_color = GREEN if meter_ok else RED
    draw.text((95,  12), "📶", font=ef, fill=wifi_color)
    draw.text((125, 12), "⚡", font=ef, fill=meter_color)


def draw_dot_indicator(draw, total: int, current: int, y: int = 208):
    """Horizontal progress dots."""
    spacing = 14
    start_x = (240 - total * spacing) // 2
    for i in range(total):
        cx   = start_x + i * spacing + 5
        fill = GREEN if i == current else DIM
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=fill) \
            if False else None
        draw.ellipse([cx - 4, y - 4, cx + 4, y + 4], fill=fill)


# ── BaseRenderer ──────────────────────────────────────────────────────────────

class BaseRenderer:
    def __init__(self, display, state):
        self.display = display
        self.state   = state

    # ── canvas helpers ────────────────────────────────────────────────────────

    def canvas(self) -> Image.Image:
        """Fresh circular dark canvas."""
        return make_canvas()

    def show(self, img: Image.Image):
        self.display.show_image(img)

    # ── font shortcuts ────────────────────────────────────────────────────────

    def get_font(self, size=16):
        return font(size)

    def get_font_bold(self, size=16):
        return font_bold(size)

    def get_emoji_font(self, size=16):
        return font_emoji(size)

    # ── colour shortcuts (theme-aware fallbacks) ──────────────────────────────

    def get_text_color(self):
        return WHITE

    def get_selected_color(self):
        return GREEN

    # ── legacy compat (called by menus not yet updated) ───────────────────────

    def get_background(self):
        return self.canvas()

    # ── shared drawing ────────────────────────────────────────────────────────

    def draw_title(self, draw, title, subtitle="", color=GREEN,
                   title_size=17, sub_size=11):
        draw_title(draw, title, subtitle, color, title_size, sub_size)

    def draw_divider(self, draw, y, color=BORDER):
        draw_divider(draw, y, color)

    def draw_buttons(self, draw, left_label, right_label,
                     right_color=GREEN, y=183):
        draw_buttons(draw, left_label, right_label, right_color, y)

    def hit_button(self, x, y, btn_y=183):
        return hit_button(x, y, btn_y)

    def draw_status_dots(self, draw, wifi_ok, meter_ok):
        draw_status_dots(draw, wifi_ok, meter_ok)

    def wrap_text(self, text, font_obj, max_width=SAFE_W):
        words, lines, cur = text.split(), [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if font_obj.getlength(test) <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def render_message(self, message: str, font_size=16, color=WHITE):
        img  = self.canvas()
        draw = ImageDraw.Draw(img)
        f    = font_bold(font_size)
        lines = []
        for raw in message.split("\n"):
            lines.extend(self.wrap_text(raw, f, SAFE_W) or [""])

        lh          = font_size + 5
        total_h     = len(lines) * lh
        y           = CY - total_h // 2

        for line in lines:
            if line:
                lw = draw.textlength(line, font=f)
                draw.text(((240 - lw) // 2, y), line, font=f, fill=color)
            y += lh

        self.show(img)

    def draw_text_with_emoji(self, draw, pos, text, font_size=16, fill=WHITE):
        import unicodedata
        x, y = pos
        rf   = font(font_size)
        ef   = font_emoji(font_size)
        for ch in text:
            cat     = unicodedata.category(ch)
            is_emo  = ord(ch) > 0x2000 and cat in ('So', 'Sm', 'Sk', 'Mn')
            f       = ef if is_emo else rf
            draw.text((x, y), ch, font=f, fill=fill)
            x += f.getlength(ch)

    def render_loading_animation(self, message: str, duration: int = 3):
        import time
        start = time.time()
        dots  = 0
        while time.time() - start < duration:
            self.render_message(f"{message}{'.' * (dots % 4)}")
            time.sleep(0.5)
            dots += 1