"""Chart rendering components — redesigned for 240x240 circular display
Visual clarity update:
  - Larger font sizes for labels and values
  - Better spacing and positioning within circular safe area
  - Clearer axis labels and trend indicators
"""
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
            tw  = d2.textlength("Power (W)", font=font_bold(17))
            d2.text(((240-tw)//2, 26), "Power (W)", font=font_bold(17), fill=T["CYAN"])
            mw  = d2.textlength("No phase data yet", font=font(14))
            d2.text(((240-mw)//2, CY-10), "No phase data yet", font=font(14), fill=T["DIM"])
            self.display.show_image(img)
            return

        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        # Title — larger
        fb = font_bold(17)
        tw = draw.textlength("Power (W)", font=fb)
        draw.text(((240 - tw) // 2, 26), "Power (W)", font=fb, fill=T["CYAN"])

        # Chart area — safe inside circle
        bar_w      = 38
        gap        = 18
        n          = len(phases)
        total_w    = n * bar_w + (n - 1) * gap
        start_x    = (240 - total_w) // 2
        origin_y   = 182
        max_bar_h  = 105
        max_power  = max([p.get("power", 0) for p in phases] + [1])

        # Phase colors — cyan palette
        colors = [T["CYAN"], T["ORANGE"], (130, 80, 255)]

        fr12 = font(12)
        fb13 = font_bold(13)

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

            # Power value above bar — larger, bolder
            val_txt = f"{power:.0f}"
            vw      = draw.textlength(val_txt, font=fb13)
            draw.text((x + (bar_w - vw) // 2, bar_top - 18),
                      val_txt, font=fb13, fill=col)

            # Phase label below bar — larger
            lbl   = f"P{i + 1}"
            lbl_w = draw.textlength(lbl, font=fr12)
            draw.text((x + (bar_w - lbl_w) // 2, origin_y + 4),
                      lbl, font=fr12, fill=T["DIM"])

        # Baseline
        draw.line([(start_x - 4, origin_y), (start_x + total_w + 4, origin_y)],
                  fill=T["BORDER"], width=1)

        # Tap hint — slightly larger
        fh = font(10)
        hw = draw.textlength("Tap: next view", font=fh)
        draw.text(((240 - hw) // 2, 214), "Tap: next view",
                  font=fh, fill=T["DIM"])

        self.display.show_image(img)

    # ── Trend line chart ──────────────────────────────────────────────────────
    def draw_trend_chart(self, draw, data, y_start, height, label):
        """Compact trend line with filled area — Dione Protocol style.
 
        Matches display-engine.js renderEnergyStats():
          - Bordered chart box
          - Trend line in CYAN
          - Filled area under curve (CYAN at ~10% opacity)
          - Axis labels (max/min) on the left outside the box
          - Time label centred below
 
        Drawn onto an existing draw context (caller's canvas).
        """
        T = self._theme()
 
        if not data or len(data) < 2:
            fh  = font(13)
            msg = f"No {label} data yet"
            mw  = draw.textlength(msg, font=fh)
            draw.text(((240 - mw) // 2, y_start + height // 2 - 6),
                      msg, font=fh, fill=T["DIM"])
            return
 
        powers = [d.get('totalPower', 0) for d in data]
        if not any(powers):
            fh  = font(13)
            msg = f"All {label} values zero"
            mw  = draw.textlength(msg, font=fh)
            draw.text(((240 - mw) // 2, y_start + height // 2 - 6),
                      msg, font=fh, fill=T["DIM"])
            return
 
        max_p = max(powers)
        min_p = min(p for p in powers if p > 0) if any(p > 0 for p in powers) else 0
        rng   = max_p - min_p if max_p != min_p else 1e-3
 
        # Chart box — centred, safe inside circle (matches JS: cW=130)
        chart_w = 130
        cl      = (240 - chart_w) // 2        # left edge
        cr      = cl + chart_w                 # right edge
        ct      = y_start                      # top
        cb      = y_start + height             # bottom
 
        # ── Border rectangle (matches JS ctx.strokeRect) ──────────────────────
        draw.rectangle([(cl, ct), (cr, cb)], outline=T["BORDER"], width=1)
 
        # ── Build point list ──────────────────────────────────────────────────
        pts = []
        n = len(powers)
        for i, p in enumerate(powers):
            x = cl + int(i * chart_w / (n - 1))
            y = cb - int(((p - min_p) / rng) * height)
            # Clamp inside chart box
            y = max(ct, min(cb, y))
            pts.append((x, y))
 
        # ── Filled area under curve ───────────────────────────────────────────
        # JS does: stroke the line, then lineTo bottom-right, lineTo bottom-left,
        # closePath, fill with rgba(CYAN, 0.1)
        #
        # In PIL we build a polygon: line points + bottom-right + bottom-left
        # and fill with a blended colour (CYAN at 10% over BG)
        if len(pts) >= 2:
            fill_pts = list(pts) + [(cr, cb), (cl, cb)]
            # Blend CYAN at 10% opacity over BG
            bg  = T["BG"]
            cyan = T["CYAN"]
            fill_col = tuple(
                int(bg[i] * 0.9 + cyan[i] * 0.1)
                for i in range(3)
            )
            draw.polygon(fill_pts, fill=fill_col)
 
        # ── Trend line (on top of fill) ───────────────────────────────────────
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i + 1]], fill=T["CYAN"], width=2)
 
        # ── Axis labels — left side, outside box (matches JS textAlign='right')
        fb11 = font_bold(11)
        fr9  = font(9)
 
        # Max value label — top-left of chart
        max_txt = f"{max_p:.0f}W"
        mw = draw.textlength(max_txt, font=fr9)
        draw.text((cl - mw - 2, ct), max_txt, font=fr9, fill=T["DIM"])
 
        # Min value label — bottom-left of chart
        min_txt = f"{min_p:.0f}W" if min_p > 0 else "0W"
        nw = draw.textlength(min_txt, font=fr9)
        draw.text((cl - nw - 2, cb - 9), min_txt, font=fr9, fill=T["DIM"])
 
        # ── Time label — centred below chart ─────────────────────────────────
        fh = font(11)
        lw = draw.textlength(label, font=fh)

    # ── Line chart (kept for compat but simplified) ───────────────────────────
    def draw_line_chart(self, values):
        """Removed as requested — shows centred message."""
        T   = self._theme()
        img = self.canvas()
        d2  = ImageDraw.Draw(img)
        msg = "Use Tap to switch views"
        mw  = d2.textlength(msg, font=font(14))
        d2.text(((240-mw)//2, CY-10), msg, font=font(14), fill=T["DIM"])
        self.display.show_image(img)