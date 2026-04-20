"""Energy menu — Dione/Orion circular design v3 (redesigned)

View cycle (tap to advance):
  0 → Text metrics (swipe up/down to page through)
  1 → Power bar chart
  2 → 24h stats + trend
  3 → 7d stats + trend

Swipe left / long press → back to main menu
"""
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, font, font_bold,
                         draw_divider, draw_nav_arrows, draw_page_indicator,
                         CX, CY, SAFE_W)
from ui.components.charts import ChartRenderer
from config.constants import *

# View indices
VIEW_TEXT  = 0
VIEW_CHART = 1
VIEW_24H   = 2
VIEW_7D    = 3
VIEW_COUNT = 4   # no "current per phase" line chart


class EnergyMenu(BaseRenderer):
    def __init__(self, display, state, energy_analyzer=None):
        super().__init__(display, state)
        self.chart_renderer  = ChartRenderer(display, state)
        self.energy_analyzer = energy_analyzer
        self.view_mode       = VIEW_TEXT

    # ── main dispatcher ───────────────────────────────────────────────────────

    def render(self):
        if self.view_mode == VIEW_TEXT:
            self._render_text()
        elif self.view_mode == VIEW_CHART:
            self._render_chart()
        elif self.view_mode == VIEW_24H:
            self._render_stats("24 Hours", self.energy_analyzer.get_24h_stats()
                               if self.energy_analyzer else None,
                               self.energy_analyzer.get_chart_data_24h()
                               if self.energy_analyzer else None,
                               "24h")
        elif self.view_mode == VIEW_7D:
            self._render_stats("7 Days", self.energy_analyzer.get_7d_stats()
                               if self.energy_analyzer else None,
                               self.energy_analyzer.get_chart_data_7d()
                               if self.energy_analyzer else None,
                               "7d")

    # ── view 0: text metrics ──────────────────────────────────────────────────

    def _render_text(self):
        if not self.state.energy_metrics:
            self._render_no_data()
            return

        T    = self._theme()
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        # Title + subtitle
        self.draw_title(draw, "Energy", title_size=17)

        # Battery bar — between title and divider
        battery = self.draw_title(draw, "Energy", title_size=17)
        by = 52
        if battery is not None:
            bw2 = 68; bx = (240 - bw2) // 2
            draw.rounded_rectangle([(bx, by), (bx + bw2, by + 7)],
                                   radius=3, outline=T["DIM"], width=1)
            draw.rounded_rectangle([(bx, by), (bx + int(bw2 * battery / 100), by + 7)],
                                   radius=3, fill=T["CYAN"])
            f9 = font(9)
            draw.text((bx + bw2 + 4, by), f"{battery:.0f}%", font=f9, fill=T["CYAN"])

        # Time since last data — right aligned
        if self.energy_analyzer:
            ts  = self.energy_analyzer.get_time_since_last_data()
            f9  = font(9)
            tsw = draw.textlength(ts, font=f9)
            draw.text((30, by + 1), ts, font=f9, fill=T["DIM"])

        draw_divider(draw, 64, T)

        # Current metric — key: value with key in CYAN
        total = len(self.state.energy_metrics)
        index = self.state.current_page % total
        text  = self.state.energy_metrics[index]

        fb15 = font_bold(15)
        fr15 = font(15)

        # Split key: value BEFORE wrapping (same fix as device menu)
        rendered = []
        if ": " in text:
            key, _, val = text.partition(": ")
            key_str  = key + ": "
            kw       = int(draw.textlength(key_str, font=fb15))
            val_wrap = self.wrap_text(val, fr15, max(60, SAFE_W - kw))
            rendered.append((key, val_wrap[0] if val_wrap else val))
            for extra in val_wrap[1:]:
                rendered.append((None, "  " + extra))
        else:
            rendered.append((None, text))

        lh      = 24
        total_h = len(rendered) * lh
        y       = max(72, CY - total_h // 2)

        for (key, val) in rendered:
            if key is not None:
                key_str = key + ": "
                kw = draw.textlength(key_str, font=fb15)
                vw = draw.textlength(val,     font=fr15)
                x  = (240 - kw - vw) // 2
                draw.text((x,      y), key_str, font=fb15, fill=T["CYAN"])
                draw.text((x + kw, y), val,     font=fr15, fill=T["WHITE"])
            else:
                lw = draw.textlength(val, font=fr15)
                draw.text(((240 - lw) // 2, y), val, font=fr15, fill=T["WHITE"])
            y += lh

        # Page indicator + nav arrows — only if multiple metrics
        if total > 1:
            draw_page_indicator(draw, index + 1, total, T, y=195)
            # arrows left/right of the pill, not overlapping
            fa = font_bold(12)
            aw = draw.textlength("▲", font=fa)
            draw.text(((240 - aw) // 2 - 36, 196), "▲", font=fa, fill=T["CYAN"])
            draw.text(((240 - aw) // 2 + 32, 196), "▼", font=fa, fill=T["CYAN"])

        # View cycle hint
        fh = font(9)
        hw = draw.textlength("Tap: chart →", font=fh)
        draw.text(((240 - hw) // 2, 212), "Tap: chart →",
                  font=fh, fill=T["DIM"])

        self.show(img)

    # ── view 1: bar chart ─────────────────────────────────────────────────────

    def _render_chart(self):
        phases = self.state.energy_data.get("phases", [])
        if not phases:
            self._render_no_data()
            return
        self.chart_renderer.draw_power_chart(phases)

    # ── view 2/3: 24h / 7d stats ──────────────────────────────────────────────

    def _render_stats(self, title, stats, chart_data, label):
        if not self.energy_analyzer:
            self.render_message("No analyzer\navailable")
            return
        if not stats:
            self.render_message(f"No {label}\ndata yet")
            return

        T    = self._theme()
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        self.draw_title(draw, title, "rolling window", title_size=16, sub_size=10)
        draw_divider(draw, 55, T)

        fb12 = font_bold(12)
        fr12 = font(12)
        lh   = 19

        # Stats rows — no "Samples" row
        rows = [
            ("Avg Power", f"{stats.get('avg_power',  0):.1f} W"),
            ("Max Power", f"{stats.get('max_power',  0):.1f} W"),
            ("Min Power", f"{stats.get('min_power',  0):.1f} W"),
            ("Energy",    f"{stats.get('total_energy', 0):.2f} kWh"),
        ]

        y = 62
        for key, val in rows:
            kw = draw.textlength(key + ": ", font=fb12)
            vw = draw.textlength(val,         font=fr12)
            x  = (240 - kw - vw) // 2
            draw.text((x,      y), key + ": ", font=fb12, fill=T["CYAN"])
            draw.text((x + kw, y), val,        font=fr12, fill=T["WHITE"])
            y += lh

        # Trend chart in lower half
        self.chart_renderer.draw_trend_chart(draw, chart_data, y + 8, 52, label)

        # Tap hint
        fh = font(9)
        hw = draw.textlength("Tap: next →", font=fh)
        draw.text(((240 - hw) // 2, 212), "Tap: next →",
                  font=fh, fill=T["DIM"])

        self.show(img)

    # ── no data fallback ──────────────────────────────────────────────────────

    def _render_no_data(self):
        T    = self._theme()
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        self.draw_title(draw, "Energy", title_size=17)
        draw_divider(draw, 55, T)

        # Centred message
        fb = font_bold(14)
        fr = font(12)
        lines = ["Waiting for", "meter data..."]
        y = CY - 20
        for line in lines:
            lw = draw.textlength(line, font=fb if line == lines[0] else fr)
            f_ = fb if line == lines[0] else fr
            draw.text(((240 - lw) // 2, y), line, font=f_, fill=T["DIM"])
            y += 22

        fh = font(10)
        hw = draw.textlength("Tap: chart →", font=fh)
        draw.text(((240 - hw) // 2, 212), "Tap: chart →",
                  font=fh, fill=T["DIM"])

        self.show(img)

    # ── gestures ──────────────────────────────────────────────────────────────

    def handle_gesture(self, gesture, touch_device=None):
        if gesture == GESTURE_TAP:
            # Cycle through views
            self.view_mode = (self.view_mode + 1) % VIEW_COUNT
            self.render()

        elif gesture == GESTURE_UP:
            if self.view_mode == VIEW_TEXT and self.state.energy_metrics:
                self.state.current_page = (
                    self.state.current_page - 1) % len(self.state.energy_metrics)
            self.render()

        elif gesture == GESTURE_DOWN:
            if self.view_mode == VIEW_TEXT and self.state.energy_metrics:
                self.state.current_page = (
                    self.state.current_page + 1) % len(self.state.energy_metrics)
            self.render()

        elif gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
            self.view_mode = VIEW_TEXT
            return MENU_MAIN

        return None