"""Energy menu — Dione/Orion circular design v3 (visual clarity update)

View cycle (tap to advance):
  0 → Text metrics (swipe up/down to page through)
  1 → Power bar chart
  2 → 24h stats + trend
  3 → 7d stats + trend

Visual improvements:
  - Larger font sizes for all metric text (15→17 for values, 12→14 for stats)
  - Better vertical centering within circular safe area
  - Dynamic text wrapping for long metric values
  - Adaptive layout: key on top, value below when combined width exceeds safe area
  - Clearer page indicators and navigation hints

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

        # Title
        self.draw_title(draw, "Energy", title_size=18)

        # Battery bar — between title and divider
        battery = self._get_battery()
        by = 52
        if battery is not None:
            bw2 = 68; bx = (240 - bw2) // 2
            draw.rounded_rectangle([(bx, by), (bx + bw2, by + 7)],
                                   radius=3, outline=T["DIM"], width=1)
            fill_w = max(1, int(bw2 * min(battery, 100) / 100))
            draw.rounded_rectangle([(bx, by), (bx + fill_w, by + 7)],
                                   radius=3, fill=T["CYAN"])
            f10 = font(10)
            draw.text((bx + bw2 + 4, by - 1), f"{battery:.0f}%",
                      font=f10, fill=T["CYAN"])

        # Time since last data
        if self.energy_analyzer:
            ts  = self.energy_analyzer.get_time_since_last_data()
            f10 = font(10)
            draw.text((30, by), ts, font=f10, fill=T["DIM"])

        draw_divider(draw, 64, T)

        # Current metric — key: value with key in CYAN
        total = len(self.state.energy_metrics)
        index = self.state.current_page % total
        text  = self.state.energy_metrics[index]

        # Use size 17 bold for key, 17 regular for value — clearly readable
        fb = font_bold(18)
        fr = font(18)
        lh = 26

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
                val_lines = self.wrap_text(val, fr, SAFE_W)
                for vl in val_lines:
                    rendered.append((None, vl))
        else:
            rendered.append((None, text))

        total_h = len(rendered) * lh
        # Centre vertically between divider (64) and page indicator (185)
        content_zone = 185 - 72
        y = 72 + max(0, (content_zone - total_h) // 2)

        for (key, val) in rendered:
            if key is not None and val is not None:
                # key: value on same line
                key_str = key + ": "
                kw = draw.textlength(key_str, font=fb)
                vw = draw.textlength(val, font=fr)
                x  = (240 - kw - vw) // 2
                draw.text((x,      y), key_str, font=fb, fill=T["CYAN"])
                draw.text((x + kw, y), val,     font=fr, fill=T["WHITE"])
            elif key is not None:
                # Key-only line (label when value wraps to next line)
                kw = draw.textlength(key, font=fb)
                draw.text(((240 - kw) // 2, y), key, font=fb, fill=T["CYAN"])
            else:
                # Value-only line (wrapped continuation)
                lw = draw.textlength(val, font=fr)
                draw.text(((240 - lw) // 2, y), val, font=fr, fill=T["WHITE"])
            y += lh

        # Page indicator + nav arrows — only if multiple metrics
        if total > 1:
            draw_page_indicator(draw, index + 1, total, T, y=192)
            # arrows left/right of the pill, not overlapping
            fa = font_bold(14)
            aw = draw.textlength("▲", font=fa)
            draw.text(((240 - aw) // 2 - 38, 193), "▲", font=fa, fill=T["CYAN"])
            draw.text(((240 - aw) // 2 + 34, 193), "▼", font=fa, fill=T["CYAN"])

        # View cycle hint
        fh = font(10)
        hw = draw.textlength("Tap: chart →", font=fh)
        draw.text(((240 - hw) // 2, 214), "Tap: chart →",
                  font=fh, fill=T["DIM"])

        self.show(img)

    def _get_battery(self):
        """Extract battery value from energy data safely."""
        if hasattr(self.state, 'energy_data') and self.state.energy_data:
            return self.state.energy_data.get("battery")
        return None

    # ── view 1: bar chart ─────────────────────────────────────────────────────

    def _render_chart(self):
        phases = self.state.energy_data.get("phases", []) if self.state.energy_data else []
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

        self.draw_title(draw, title, title_size=18)
        draw_divider(draw, 56, T)

        # Increased from 12→14 for much better readability
        fb14 = font_bold(14)
        fr14 = font(14)
        lh   = 22

        # Stats rows
        rows = [
            ("Avg Power", f"{stats.get('avg_power',  0):.1f} W"),
            ("Max Power", f"{stats.get('max_power',  0):.1f} W"),
            ("Min Power", f"{stats.get('min_power',  0):.1f} W"),
            ("Energy",    f"{stats.get('total_energy', 0):.2f} kWh"),
        ]

        y = 63
        for key, val in rows:
            key_txt = key + ": "
            kw = draw.textlength(key_txt, font=fb14)
            vw = draw.textlength(val,     font=fr14)
            x  = (240 - kw - vw) // 2
            draw.text((x,      y), key_txt, font=fb14, fill=T["CYAN"])
            draw.text((x + kw, y), val,     font=fr14, fill=T["WHITE"])
            y += lh

        # Trend chart in lower half
        self.chart_renderer.draw_trend_chart(draw, chart_data, y + 6, 48, label)

        # Tap hint
        fh = font(10)
        hw = draw.textlength("Tap: next →", font=fh)
        draw.text(((240 - hw) // 2, 214), "Tap: next →",
                  font=fh, fill=T["DIM"])

        self.show(img)

    # ── no data fallback ──────────────────────────────────────────────────────

    def _render_no_data(self):
        T    = self._theme()
        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        self.draw_title(draw, "Energy", title_size=18)
        draw_divider(draw, 55, T)

        # Centred message — larger fonts
        fb = font_bold(16)
        fr = font(14)
        lines = [("Waiting for", fb), ("meter data...", fr)]
        total_h = sum(24 for _ in lines)
        y = CY - total_h // 2
        for text, f_ in lines:
            lw = draw.textlength(text, font=f_)
            draw.text(((240 - lw) // 2, y), text, font=f_, fill=T["DIM"])
            y += 24

        fh = font(10)
        hw = draw.textlength("Tap: chart →", font=fh)
        draw.text(((240 - hw) // 2, 214), "Tap: chart →",
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