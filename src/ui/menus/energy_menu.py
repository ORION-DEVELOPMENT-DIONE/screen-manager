"""Energy menu — circular Orion design"""
from PIL import ImageDraw
from ui.renderer import (BaseRenderer, GREEN, DIM, WHITE, ORANGE, SURFACE, BORDER,
                         font, font_bold, font_emoji,
                         draw_title, draw_divider, CX, CY, SAFE_W)
from ui.components.charts import ChartRenderer
from config.constants import *


class EnergyMenu(BaseRenderer):
    def __init__(self, display, state, energy_analyzer=None):
        super().__init__(display, state)
        self.chart_renderer   = ChartRenderer(display, state)
        self.energy_analyzer  = energy_analyzer
        self.view_mode        = 0   # 0=current text, 1=24h, 2=7d

    # ── render dispatcher ─────────────────────────────────────────────────────

    def render(self):
        if self.view_mode == 0:
            self._render_current()
        elif self.view_mode == 1:
            self._render_24h()
        elif self.view_mode == 2:
            self._render_7d()

    # ── current data ──────────────────────────────────────────────────────────

    def _render_current(self):
        if self.state.chart_mode == 1:
            self.chart_renderer.draw_power_chart(
                self.state.energy_data.get("phases", []))
            return
        if self.state.chart_mode == 2:
            currents = [p.get("current", 0)
                        for p in self.state.energy_data.get("phases", [])]
            self.chart_renderer.draw_line_chart(currents)
            return

        # Text mode
        if not self.state.energy_metrics:
            self.render_message("No energy\ndata yet")
            return

        img  = self.canvas()
        draw = ImageDraw.Draw(img)

        # Header
        draw_title(draw, "Energy", "Live data", GREEN)

        # Battery + time-since
        fb10 = font_bold(10)
        fr10 = font(10)
        battery = self.state.energy_data.get("battery")
        if battery is not None:
            bt = f"🔋 {battery:.0f}%"
            ef = font_emoji(11)
            draw.text((30, 54), bt, font=ef, fill=GREEN)
        if self.energy_analyzer:
            ts  = self.energy_analyzer.get_time_since_last_data()
            tsw = draw.textlength(ts, font=fr10)
            draw.text((210 - tsw, 56), ts, font=fr10, fill=DIM)

        draw_divider(draw, 66)

        # Metric text
        index = self.state.current_page % len(self.state.energy_metrics)
        fr13  = font(13)
        lines = self.wrap_text(self.state.energy_metrics[index], fr13, SAFE_W)
        lh    = 20
        total = len(lines) * lh
        y     = max(72, CY - total // 2)

        for line in lines:
            lw = draw.textlength(line, font=fr13)
            draw.text(((240 - lw) // 2, y), line, font=fr13, fill=WHITE)
            y += lh

        # Mode badge + nav arrow
        fb10 = font_bold(10)
        badge = ["Text", "Bar", "Line"][self.state.chart_mode]
        bw    = draw.textlength(badge, font=fb10)
        draw.text((210 - bw, 207), badge, font=fb10, fill=DIM)

        aw = draw.textlength("▼", font=fb10)
        draw.text(((240 - aw) // 2, 207), "▼", font=fb10, fill=DIM)

        self.show(img)

    # ── 24h stats ─────────────────────────────────────────────────────────────

    def _render_24h(self):
        if not self.energy_analyzer:
            self.render_message("No analyzer"); return
        stats = self.energy_analyzer.get_24h_stats()
        if not stats:
            self.render_message("No 24h data\nyet"); return

        img  = self.canvas()
        draw = ImageDraw.Draw(img)
        draw_title(draw, "24 Hours", "rolling window", GREEN)
        draw_divider(draw, 54)
        self._draw_stats(draw, stats, 62)

        # Mini chart
        chart_data = self.energy_analyzer.get_chart_data_24h()
        self.chart_renderer.draw_trend_chart(draw, chart_data, 155, 50, "24h")

        self.show(img)

    # ── 7d stats ──────────────────────────────────────────────────────────────

    def _render_7d(self):
        if not self.energy_analyzer:
            self.render_message("No analyzer"); return
        stats = self.energy_analyzer.get_7d_stats()
        if not stats:
            self.render_message("No 7d data\nyet"); return

        img  = self.canvas()
        draw = ImageDraw.Draw(img)
        draw_title(draw, "7 Days", "rolling window", GREEN)
        draw_divider(draw, 54)
        self._draw_stats(draw, stats, 62)

        chart_data = self.energy_analyzer.get_chart_data_7d()
        self.chart_renderer.draw_trend_chart(draw, chart_data, 155, 50, "7d")

        self.show(img)

    # ── shared stats drawer ───────────────────────────────────────────────────

    def _draw_stats(self, draw, stats, y_start):
        fb = font_bold(12)
        fr = font(12)
        lh = 19
        rows = [
            ("Avg Power",    f"{stats.get('avg_power',0):.1f} W"),
            ("Max Power",    f"{stats.get('max_power',0):.1f} W"),
            ("Min Power",    f"{stats.get('min_power',0):.1f} W"),
            ("Energy",       f"{stats.get('total_energy',0):.2f} kWh"),
            ("Samples",      str(stats.get('data_points', 0))),
        ]
        y = y_start
        for key, val in rows:
            kw  = draw.textlength(key + ": ", font=fb)
            vw  = draw.textlength(val, font=fr)
            x   = (240 - kw - vw) // 2
            draw.text((x, y), key + ": ", font=fb, fill=GREEN)
            draw.text((x + kw, y), val,   font=fr,  fill=WHITE)
            y  += lh

    # ── gestures ──────────────────────────────────────────────────────────────

    def handle_gesture(self, gesture, touch_device=None):
        if not self.state.energy_metrics and self.view_mode == 0:
            if gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
                return MENU_MAIN
            return None

        if gesture == GESTURE_UP:
            if self.view_mode == 0:
                self.state.current_page = (
                    self.state.current_page - 1) % len(self.state.energy_metrics)
            self.render()
        elif gesture == GESTURE_DOWN:
            if self.view_mode == 0:
                self.state.current_page = (
                    self.state.current_page + 1) % len(self.state.energy_metrics)
            self.render()
        elif gesture == GESTURE_TAP:
            if self.view_mode < 2:
                self.view_mode += 1
            else:
                self.view_mode = 0
                self.state.chart_mode = (self.state.chart_mode + 1) % 3
            self.render()
        elif gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
            self.view_mode = 0
            return MENU_MAIN

        return None