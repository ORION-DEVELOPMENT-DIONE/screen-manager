"""
ui/renderer.py  —  Orion · Dione Protocol  circular design system
Visual clarity update:
  - Improved wrap_text: handles long single words (WiFi SSIDs) by char-splitting
  - Larger nav arrows and page indicators for readability
  - Smarter text positioning within circular safe area
  - render_message uses adaptive font sizing
"""
import math
from PIL import Image, ImageDraw, ImageFont
from config.constants import *

# ── Dark mode tokens ──────────────────────────────────────────────────────────
DARK = dict(
    BG        = (4,    8,   20),
    BG2       = (8,   14,   32),
    SURFACE   = (16,  26,   54),
    BORDER    = (28,  45,   90),
    CYAN      = (0,  220,  200),
    CYAN_DIM  = (0,   80,   74),
    ORANGE    = (255, 160,   0),
    RED       = (220,  55,   65),
    VIOLET    = (130,  80,  255),
    WHITE     = (230, 238,  248),
    DIM       = (100, 115,  150),
    STAR      = (160, 180,  210),
    NODE      = (0,  200,  185),
    NODE_DIM  = (0,   45,   42),
    GRID      = (10,  20,   44),
)

# ── Light mode tokens ─────────────────────────────────────────────────────────
LIGHT = dict(
    BG        = (225, 242,  255),
    BG2       = (205, 228,  250),
    SURFACE   = (185, 215,  245),
    BORDER    = (130, 178,  218),
    CYAN      = (0,  140,  170),
    CYAN_DIM  = (90, 160,  195),
    ORANGE    = (205, 105,   0),
    RED       = (185,  25,   38),
    VIOLET    = (95,   45,  215),
    WHITE     = (8,   18,   48),
    DIM       = (65,   88,  125),
    STAR      = (140, 170,  205),
    NODE      = (0,  140,  170),
    NODE_DIM  = (155, 195,  222),
    GRID      = (195, 222,  242),
)

CX = CY = 120
R       = 118
SAFE_W  = 172    # increased from 160 — better use of the ~192px usable band

# ── Font paths ────────────────────────────────────────────────────────────────
_SYMBOLA = "/home/orangepi/screen-manager/Font/Symbola.ttf"
_DJVU    = "/home/orangepi/screen-manager/Font/DejaVuSans.ttf"
_DJVUB   = "/home/orangepi/screen-manager/Font/DejaVuSans-Bold.ttf"

# Preview/CI fallbacks
_SYMBOLA_PREVIEW = "/home/claude/screen-manager-development/Font/Symbola.ttf"
_DJVU_PREVIEW    = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DJVUB_PREVIEW   = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _load(candidates, size):
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def font(size=15):
    return _load([_DJVU, _DJVU_PREVIEW], size)

def font_bold(size=15):
    return _load([_DJVUB, _DJVUB_PREVIEW, _DJVU, _DJVU_PREVIEW], size)

def font_emoji(size=20):
    return _load([_SYMBOLA, _SYMBOLA_PREVIEW, _DJVU, _DJVU_PREVIEW], size)


# ── Starfield (deterministic, small) ─────────────────────────────────────────
_STARS = []

def _gen_stars(n=35, seed=42):
    global _STARS
    _STARS = []
    x, y = seed, seed * 7
    for _ in range(n):
        x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
        y = (y * 22695477 + 1)         & 0xFFFFFFFF
        sx = (x % 210) + 15
        sy = (y % 210) + 15
        if math.hypot(sx - CX, sy - CY) < R - 8:
            # only 1px stars — never 2px to avoid interfering with text
            _STARS.append((sx, sy))

_gen_stars()

# ── Bezel nodes ───────────────────────────────────────────────────────────────
_NODE_COUNT  = 12
_NODE_ANGLES = [i * 360 / _NODE_COUNT for i in range(_NODE_COUNT)]
_ACTIVE_NODES = {0, 3, 6, 9}


# ── Canvas builder ────────────────────────────────────────────────────────────

def make_canvas(T: dict) -> Image.Image:
    img  = Image.new("RGB", (240, 240), T["BG"])
    draw = ImageDraw.Draw(img)

    # 1. Radial gradient
    bg, bg2 = T["BG"], T["BG2"]
    for ring in range(R, 0, -4):          # step=4 for speed
        t  = ring / R
        rc = tuple(int(bg[i] * t + bg2[i] * (1 - t)) for i in range(3))
        draw.ellipse([CX-ring, CY-ring, CX+ring, CY+ring], outline=rc)

    # 2. Subtle hex grid
    hs = 24
    for row in range(-1, 12):
        for col in range(-1, 12):
            hx = col * hs * 1.73
            hy = row * hs * 2 + (col % 2) * hs
            if math.hypot(hx - CX, hy - CY) > R + hs:
                continue
            pts = []
            for a in range(6):
                ang = math.radians(60 * a - 30)
                pts.append((hx + hs * 0.55 * math.cos(ang),
                             hy + hs * 0.55 * math.sin(ang)))
            draw.polygon(pts, outline=T["GRID"])

    # 3. Stars — tiny 1px dots only
    for (sx, sy) in _STARS:
        draw.point((sx, sy), fill=T["STAR"])

    # 4. Bezel node ring — dots only, NO lines to centre
    nr = R - 5
    for i, ang_deg in enumerate(_NODE_ANGLES):
        ang = math.radians(ang_deg - 90)
        nx  = int(CX + nr * math.cos(ang))
        ny  = int(CY + nr * math.sin(ang))
        if i in _ACTIVE_NODES:
            # subtle glow
            draw.ellipse([nx-4, ny-4, nx+4, ny+4], fill=T["CYAN_DIM"])
            draw.ellipse([nx-2, ny-2, nx+2, ny+2], fill=T["NODE"])
        else:
            draw.ellipse([nx-1, ny-1, nx+1, ny+1], fill=T["NODE_DIM"])

    # 5. Circular clip
    mask = Image.new("L", (240, 240), 0)
    ImageDraw.Draw(mask).ellipse([CX-R, CY-R, CX+R, CY+R], fill=255)
    black = Image.new("RGB", (240, 240), (0, 0, 0))
    black.paste(img, mask=mask)
    return black


# ── Shared drawing primitives ─────────────────────────────────────────────────

def draw_title(draw, title: str, subtitle: str = "",
               color=None, theme: dict = DARK,
               title_size=17, sub_size=11):
    if color is None:
        color = theme["CYAN"]
    tf = font_bold(title_size)
    tw = draw.textlength(title, font=tf)
    draw.text(((240 - tw) // 2, 26), title, font=tf, fill=color)
    if subtitle:
        sf = font(sub_size)
        sw = draw.textlength(subtitle, font=sf)
        draw.text(((240 - sw) // 2, 26 + title_size + 4),
                  subtitle, font=sf, fill=theme["DIM"])


def draw_divider(draw, y: int, theme: dict = DARK):
    w = 72
    draw.line([(CX - w, y), (CX + w, y)], fill=theme["BORDER"], width=1)
    draw.ellipse([CX-w-2, y-1, CX-w+2, y+1], fill=theme["CYAN_DIM"])
    draw.ellipse([CX+w-2, y-1, CX+w+2, y+1], fill=theme["CYAN_DIM"])


def draw_buttons(draw, left_label: str, right_label: str,
                 right_color=None, theme: dict = DARK, y: int = 181):
    if right_color is None:
        right_color = theme["CYAN"]
    bw, bh, gap = 86, 34, 8
    total = 2 * bw + gap
    sx    = (240 - total) // 2
    rx    = sx + bw + gap
    fb    = font_bold(13)

    # Left pill
    draw.rounded_rectangle([(sx, y), (sx+bw, y+bh)],
                            radius=9, outline=theme["DIM"], width=1)
    lw = draw.textlength(left_label, font=fb)
    draw.text((sx + (bw-lw)//2, y + (bh-13)//2),
              left_label, font=fb, fill=theme["DIM"])

    # Right pill — glowing
    inner = tuple(min(255, c // 5) for c in right_color)
    draw.rounded_rectangle([(rx, y), (rx+bw, y+bh)],
                            radius=9, outline=right_color, width=2)
    draw.rounded_rectangle([(rx+1, y+1), (rx+bw-1, y+bh-1)],
                            radius=8, fill=inner)
    rw = draw.textlength(right_label, font=fb)
    draw.text((rx + (bw-rw)//2, y + (bh-13)//2),
              right_label, font=fb, fill=right_color)


def hit_button(x, y, btn_y=181, bw=86, bh=34, gap=8):
    total = 2 * bw + gap
    sx    = (240 - total) // 2
    rx    = sx + bw + gap
    if btn_y <= y <= btn_y + bh:
        if sx <= x <= sx + bw:   return "left"
        if rx <= x <= rx + bw:   return "right"
    return None


def draw_status_bar(draw, wifi_ok: bool, meter_ok: bool, theme: dict = DARK):
    """Emoji status bar — 📶 and ⚡ with green/red coloring."""
    ef          = font_emoji(20)
    wifi_color  = (46, 204, 113) if wifi_ok  else (231, 76,  60)
    meter_color = (46, 204, 113) if meter_ok else (231, 76,  60)

    wifi_w  = ef.getlength("📶")
    bolt_w  = ef.getlength("⚡")
    draw.text((105 - int(wifi_w)  // 2, 10), "📶", font=ef, fill=wifi_color)
    draw.text((135 - int(bolt_w)  // 2, 10), "⚡", font=ef, fill=meter_color)

# keep old name working
draw_status_dots = draw_status_bar


def draw_corner_hash(draw, label: str, theme: dict = DARK):
    fr = font(9)
    hw = draw.textlength(label, font=fr)
    draw.text((CX - hw//2, 217), label, font=fr, fill=theme["DIM"])


def draw_nav_arrows(draw, theme: dict = DARK, show_up=True, show_down=True,
                    up_y=56, down_y=207):
    """Clearly visible navigation arrows — larger for readability."""
    fb = font_bold(14)
    aw = draw.textlength("▲", font=fb)
    cx = (240 - aw) // 2
    if show_up:
        draw.text((cx, up_y), "▲", font=fb, fill=theme["CYAN"])
    if show_down:
        draw.text((cx, down_y), "▼", font=fb, fill=theme["CYAN"])


def draw_page_indicator(draw, current: int, total: int,
                        theme: dict = DARK, y: int = 207):
    """Page number indicator — larger pill, bolder text for clarity."""
    fb  = font_bold(13)
    txt = f"{current}/{total}"
    tw  = draw.textlength(txt, font=fb)
    # pill background — slightly bigger padding
    draw.rounded_rectangle(
        [(CX - tw//2 - 10, y - 3), (CX + tw//2 + 10, y + 16)],
        radius=6, fill=theme["SURFACE"]
    )
    draw.text((CX - tw//2, y), txt, font=fb, fill=theme["CYAN"])


# ── BaseRenderer ──────────────────────────────────────────────────────────────

class BaseRenderer:
    def __init__(self, display, state):
        self.display = display
        self.state   = state

    def _theme(self) -> dict:
        if hasattr(self.state, "active_theme"):
            if getattr(self.state.active_theme, "name", "dark") == "light":
                return LIGHT
        return DARK

    # ── canvas ────────────────────────────────────────────────────────────────

    def canvas(self) -> Image.Image:
        return make_canvas(self._theme())

    def show(self, img: Image.Image):
        self.display.show_image(img)

    # ── backward compat ───────────────────────────────────────────────────────

    def get_background(self) -> Image.Image:
        return self.canvas()

    def get_font(self, size=15):        return font(size)
    def get_font_bold(self, size=15):   return font_bold(size)
    def get_emoji_font(self, size=20):  return font_emoji(size)
    def get_text_color(self):           return self._theme()["WHITE"]
    def get_selected_color(self):       return self._theme()["CYAN"]

    # ── primitives ────────────────────────────────────────────────────────────

    def draw_title(self, draw, title, subtitle="", color=None,
                   title_size=17, sub_size=11):
        draw_title(draw, title, subtitle, color, self._theme(),
                   title_size, sub_size)

    def draw_divider(self, draw, y):
        draw_divider(draw, y, self._theme())

    def draw_buttons(self, draw, left_label, right_label,
                     right_color=None, y=181):
        draw_buttons(draw, left_label, right_label,
                     right_color, self._theme(), y)

    def hit_button(self, x, y, btn_y=181):
        return hit_button(x, y, btn_y)

    def draw_status_bar(self, draw, wifi_ok, meter_ok):
        draw_status_bar(draw, wifi_ok, meter_ok, self._theme())

    # keep old name
    def draw_status_dots(self, draw, wifi_ok, meter_ok):
        draw_status_bar(draw, wifi_ok, meter_ok, self._theme())

    def draw_nav_arrows(self, draw, show_up=True, show_down=True,
                        up_y=56, down_y=207):
        draw_nav_arrows(draw, self._theme(), show_up, show_down, up_y, down_y)

    def draw_page_indicator(self, draw, current, total, y=207):
        draw_page_indicator(draw, current, total, self._theme(), y)

    # ── text ─────────────────────────────────────────────────────────────────

    def wrap_text(self, text, font_obj, max_width=SAFE_W):
        """Word-wrap text, with character-level fallback for long words.

        If a single word is wider than max_width (e.g. a long WiFi SSID
        like 'MyVeryLongNetworkName_5GHz_Extended'), it gets split across
        lines at character boundaries so it never overflows the screen.
        """
        words = text.split()
        lines = []
        cur   = ""
        for w in words:
            test = (cur + " " + w).strip()
            if font_obj.getlength(test) <= max_width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                # Check if the word itself fits on one line
                if font_obj.getlength(w) <= max_width:
                    cur = w
                else:
                    # Character-level split for very long words
                    cur = ""
                    for ch in w:
                        test_ch = cur + ch
                        if font_obj.getlength(test_ch) <= max_width:
                            cur = test_ch
                        else:
                            if cur:
                                lines.append(cur)
                            cur = ch
        if cur:
            lines.append(cur)
        return lines

    def render_message(self, message: str, font_size=16, color=None):
        """Render a centred message — auto-shrinks font if text overflows."""
        T = self._theme()
        if color is None:
            color = T["WHITE"]
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        # Try the requested size first; shrink if lines don't fit vertically
        size = font_size
        while size >= 11:
            fb    = font_bold(size)
            lines = []
            for raw in message.split("\n"):
                lines.extend(self.wrap_text(raw, fb, SAFE_W) or [""])
            lh      = size + 7
            total_h = len(lines) * lh
            if total_h <= 160:   # fits in safe vertical area
                break
            size -= 1

        fb = font_bold(size)
        lh = size + 7
        lines_wrapped = []
        for raw in message.split("\n"):
            lines_wrapped.extend(self.wrap_text(raw, fb, SAFE_W) or [""])
        total_h = len(lines_wrapped) * lh
        y       = CY - total_h // 2

        for line in lines_wrapped:
            if line:
                lw = draw.textlength(line, font=fb)
                draw.text(((240 - lw) // 2, y), line, font=fb, fill=color)
            y += lh
        self.show(img)

    def draw_text_with_emoji(self, draw, pos, text, font_size=15, fill=None):
        import unicodedata
        T = self._theme()
        if fill is None:
            fill = T["WHITE"]
        x, y = pos
        rf = font(font_size)
        ef = font_emoji(font_size)
        for ch in text:
            cat    = unicodedata.category(ch)
            is_emo = ord(ch) > 0x2000 and cat in ('So', 'Sm', 'Sk', 'Mn')
            f      = ef if is_emo else rf
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