"""Chart rendering components — redesigned for 240x240 circular display"""
from PIL import ImageDraw
from ui.renderer import BaseRenderer, font, font_bold, DARK, CX, CY, R
from config.constants import SCREEN_WIDTH, SCREEN_HEIGHT


class ChartRenderer(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)

    # ── Power bar chart ───────────────────────────────────────────────────────

    def draw_power_chart(self, phases):
        """3-bar chart for phase power — circular-safe layout."""
        T = self._theme()

        if not phases:
            T   = self._theme()
            img = self.canvas()
            d2  = ImageDraw.Draw(img)
            tw  = d2.textlength("Power (W)", font=font_bold(15))
            d2.text(((240-tw)//2, 26), "Power (W)", font=font_bold(15), fill=T["CYAN"])
            mw  = d2.textlength("No phase data yet", font=font(13))
            d2.text(((240-mw)//2, CY-10), "No phase data yet", font=font(13), fill=T["DIM"])
            self.display.show_image(img)
            return

        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        # Title
        fb = font_bold(15)
        tw = draw.textlength("Power (W)", font=fb)
        draw.text(((240 - tw) // 2, 26), "Power (W)", font=fb, fill=T["CYAN"])

        # Chart area — safe inside circle
        bar_w      = 38
        gap        = 18
        n          = len(phases)
        total_w    = n * bar_w + (n - 1) * gap
        start_x    = (240 - total_w) // 2
        origin_y   = 185
        max_bar_h  = 110
        max_power  = max([p.get("power", 0) for p in phases] + [1])

        # Phase colors — cyan palette instead of raw red/green/blue
        colors = [T["CYAN"], T["ORANGE"], (130, 80, 255)]

        fr10 = font(10)
        fb11 = font_bold(11)

        for i, phase in enumerate(phases):
            power      = phase.get("power", 0)
            bar_height = max(4, int((power / max_power) * max_bar_h))
            x          = start_x + i * (bar_w + gap)
            bar_top    = origin_y - bar_height
            col        = colors[i % len(colors)]

            # Bar with rounded top
            draw.rounded_rectangle(
                [(x, bar_top), (x + bar_w, origin_y)],
                radius=4, fill=col
            )

            # Power value above bar
            val_txt = f"{power:.0f}"
            vw      = draw.textlength(val_txt, font=fb11)
            draw.text((x + (bar_w - vw) // 2, bar_top - 16),
                      val_txt, font=fb11, fill=col)

            # Phase label below bar
            lbl   = f"P{i + 1}"
            lbl_w = draw.textlength(lbl, font=fr10)
            draw.text((x + (bar_w - lbl_w) // 2, origin_y + 4),
                      lbl, font=fr10, fill=T["DIM"])

        # Baseline
        draw.line([(start_x - 4, origin_y), (start_x + total_w + 4, origin_y)],
                  fill=T["BORDER"], width=1)

        # Tap hint
        fh = font(10)
        hw = draw.textlength("Tap: next view", font=fh)
        draw.text(((240 - hw) // 2, 210), "Tap: next view",
                  font=fh, fill=T["DIM"])

        self.display.show_image(img)

    # ── Trend line chart ──────────────────────────────────────────────────────

    def draw_trend_chart(self, draw, data, y_start, height, label):
        """Compact trend line — drawn onto an existing draw context."""
        T = self._theme()

        if not data or len(data) < 2:
            fh = font(11)
            msg = f"No {label} data yet"
            mw  = draw.textlength(msg, font=fh)
            draw.text(((240 - mw) // 2, y_start + height // 2 - 6),
                      msg, font=fh, fill=T["DIM"])
            return

        powers = [d.get('totalPower', 0) for d in data]
        if not any(powers):
            fh  = font(11)
            msg = f"All {label} values zero"
            mw  = draw.textlength(msg, font=fh)
            draw.text(((240 - mw) // 2, y_start + height // 2 - 6),
                      msg, font=fh, fill=T["DIM"])
            return

        max_p = max(powers)
        min_p = min(p for p in powers if p > 0) if any(p > 0 for p in powers) else 0
        scale = height / (max_p - min_p + 1e-3)

        # Chart area — centred, safe inside circle
        chart_w = 160
        cl      = (240 - chart_w) // 2       # left edge
        cr      = cl + chart_w               # right edge
        cb      = y_start + height           # bottom

        # Axes
        draw.line([(cl, y_start), (cl, cb)], fill=T["DIM"], width=1)
        draw.line([(cl, cb), (cr, cb)],      fill=T["DIM"], width=1)

        # Trend line
        pts = []
        for i, p in enumerate(powers):
            x = cl + int(i * chart_w / (len(powers) - 1))
            y = cb - int((p - min_p) * scale)
            pts.append((x, y))

        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i + 1]], fill=T["CYAN"], width=2)

        # Min/max labels
        fb10 = font_bold(10)
        draw.text((cl + 3, y_start),    f"{max_p:.0f}W", font=fb10, fill=T["CYAN"])
        draw.text((cl + 3, cb - 13),    f"{min_p:.0f}W", font=fb10, fill=T["DIM"])

        # Label
        fh = font(10)
        lw = draw.textlength(label, font=fh)
        draw.text(((240 - lw) // 2, y_start - 14), label, font=fh, fill=T["DIM"])

    # ── Line chart (kept for compat but simplified) ───────────────────────────

    def draw_line_chart(self, values):
        """Removed as requested — shows centred message."""
        T   = self._theme()
        img = self.canvas()
        d2  = ImageDraw.Draw(img)
        msg = "Use Tap to switch views"
        mw  = d2.textlength(msg, font=font(13))
        d2.text(((240-mw)//2, CY-10), msg, font=font(13), fill=T["DIM"])
        self.display.show_image(img)