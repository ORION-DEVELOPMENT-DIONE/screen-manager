#!/usr/bin/env python3
"""
hardware_gesture_test.py
========================
Real hardware test for CST816S MotionMask continuous scroll.

    cd ~/screen-manager/screen-manager-development/src
    sudo python3 hardware_gesture_test.py

How MotionMask works here
--------------------------
With 0xEC = 0x07 written, the IC fires a new GestureID interrupt on every
NorScanPer tick (default 10ms) WHILE the finger is still moving.
So a slow 300ms swipe produces ~30 events instead of 1.

The debounce window (SCROLL_LOCKOUT_S = 0.35s) means:
  - First event of a swipe  → accepted, selected_option changes, screen renders
  - All subsequent events within 0.35s for the SAME gesture → ignored
  - Next DIFFERENT gesture (e.g. UP after DOWN) → always accepted immediately

This gives one item per intentional swipe, regardless of finger speed,
while still feeling instant because the render fires on the FIRST event
(not at finger-lift like the old code).

The double-render bug from the old version is also fixed:
handle_gesture() calls render() internally — the loop must NOT call it again.
"""

import sys, os

# ── Path fix ──────────────────────────────────────────────────────────────────
_src_dir  = os.path.dirname(os.path.abspath(__file__))
_repo_dir = os.path.abspath(os.path.join(_src_dir, ".."))
sys.path.insert(0, _src_dir)
sys.path.append(_repo_dir)

import time, logging, threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gesture_test")

from config.constants import (
    GESTURE_UP, GESTURE_DOWN, GESTURE_TAP, GESTURE_LONG_PRESS,
    MENU_MAIN, TP_INT,
)
from utils.state import AppState
from core.display import DisplayManager
from ui.menus.main_menu import MainMenu
from lib import LCD_1inch28 as LCD_module, Touch_1inch28 as Touch_module

REG_MOTION_MASK = 0xEC
REG_DIS_SLEEP   = 0xFE
REG_IRQ_CTL     = 0xFA

GESTURE_NAMES = {
    GESTURE_UP:         "SWIPE UP   (prev)",
    GESTURE_DOWN:       "SWIPE DOWN (next)",
    GESTURE_TAP:        "TAP        (select)",
    GESTURE_LONG_PRESS: "LONG PRESS (back)",
    0x03:               "SWIPE LEFT",
    0x04:               "SWIPE RIGHT",
    0x0B:               "DOUBLE TAP",
}


class OrionTouch(Touch_module.Touch_1inch28):
    def configure_motion_mask(self):
        self.Touch_Write_Byte(REG_MOTION_MASK, 0x07)  # EnConLR|EnConUD|EnDClick
        self.Touch_Write_Byte(REG_DIS_SLEEP,   0x01)  # keep IC awake
        self.Touch_Write_Byte(REG_IRQ_CTL,     0x50)  # EnTouch|EnMotion
        readback = self.Touch_Read_Byte(REG_MOTION_MASK)
        log.info("MotionMask written: 0x07  readback: 0x%02X  %s",
                 readback, "OK" if readback == 0x07 else "MISMATCH")


class InstrumentedDisplay(DisplayManager):
    def __init__(self, disp):
        super().__init__(disp)
        self.render_n    = 0
        self._gesture_ts = 0.0
        self._latencies  = []

    def mark_gesture(self):
        self._gesture_ts = time.monotonic()

    def show_image(self, image):
        t0 = time.monotonic()
        super().show_image(image)
        spi_ms = (time.monotonic() - t0) * 1000
        self.render_n += 1
        if self._gesture_ts > 0:
            lag = (time.monotonic() - self._gesture_ts) * 1000
            self._latencies.append(lag)
            self._gesture_ts = 0.0
            log.info("render #%-3d  SPI=%4.0fms  gesture->pixel=%4.0fms",
                     self.render_n, spi_ms, lag)
        else:
            log.info("render #%-3d  SPI=%4.0fms", self.render_n, spi_ms)

    def latency_summary(self):
        s = self._latencies
        if not s:
            return "no scroll samples"
        return (f"n={len(s)}"
                f"  avg={sum(s)/len(s):.0f}ms"
                f"  min={min(s):.0f}ms"
                f"  max={max(s):.0f}ms")


def main():
    log.info("=" * 55)
    log.info("ORION Hardware Gesture Test — MotionMask scroll")
    log.info("=" * 55)

    raw_lcd = LCD_module.LCD_1inch28()
    raw_lcd.Init()
    raw_lcd.clear()
    log.info("LCD ready")

    touch = OrionTouch()
    touch.init()
    touch.configure_motion_mask()

    state   = AppState()
    display = InstrumentedDisplay(raw_lcd)
    menu    = MainMenu(display, state)

    # ── IRQ callback — only reads GestureID, nothing else ────────────────────
    def interrupt_callback():
        touch.Gestures = touch.Touch_Read_Byte(0x01)
        state.last_activity_time = time.time()

    touch.int_irq(TP_INT, interrupt_callback)
    log.info("IRQ attached on pin %d", TP_INT)

    menu.render()
    log.info("Ready — swipe up/down, tap to select, long-press to reset. Ctrl-C to quit.")
    log.info("")

    # ── Timing constants ──────────────────────────────────────────────────────
    # SCROLL_LOCKOUT_S: after a scroll gesture is accepted, ignore further
    # events for this many seconds FOR THE SAME DIRECTION.
    # This is what gives "one item per swipe" with MotionMask continuous events.
    # Lower = more sensitive (can multi-step on fast flings).
    # Higher = more sluggish feeling.
    # 0.35s is a good starting point — adjust to taste on the real screen.
    SCROLL_LOCKOUT_S = 0.35

    # TAP/LONG_PRESS don't need lockout — they are inherently single events.
    TAP_DEBOUNCE_S   = 0.20

    last_accepted_gesture  = None
    last_accepted_time     = 0.0

    try:
        while True:
            gesture = touch.Gestures

            if gesture == 0:
                time.sleep(0.02)
                continue

            now = time.time()
            touch.Gestures = 0  # clear immediately so we don't re-process

            is_scroll = gesture in (GESTURE_UP, GESTURE_DOWN, 0x03, 0x04)
            is_tap    = gesture in (GESTURE_TAP, 0x0B)

            # ── Lockout logic ─────────────────────────────────────────────────
            elapsed = now - last_accepted_time
            same    = (gesture == last_accepted_gesture)

            if is_scroll and same and elapsed < SCROLL_LOCKOUT_S:
                # Continuous MotionMask event for the SAME direction within
                # lockout window — ignore it (this prevents double-stepping)
                continue

            if is_tap and same and elapsed < TAP_DEBOUNCE_S:
                continue

            # ── Accept this gesture ───────────────────────────────────────────
            last_accepted_gesture = gesture
            last_accepted_time    = now
            display.mark_gesture()

            log.info("0x%02X  %-20s  selected=%d",
                     gesture,
                     GESTURE_NAMES.get(gesture, "unknown"),
                     state.selected_option)

            if gesture == GESTURE_LONG_PRESS:
                state.current_menu    = MENU_MAIN
                state.selected_option = 0
                # handle_gesture won't be called so we render manually
                menu.render()
                continue

            # handle_gesture() updates selected_option AND calls render()
            # internally — do NOT call menu.render() again after this
            result = menu.handle_gesture(gesture, touch)

            if result is not None:
                log.info("-> navigating to menu %d (bouncing back for test)", result)
                state.current_menu = result
                time.sleep(0.4)
                state.current_menu    = MENU_MAIN
                state.selected_option = 0
                menu.render()

    except KeyboardInterrupt:
        pass

    log.info("")
    log.info("=" * 55)
    log.info("Latency  : %s", display.latency_summary())
    log.info("Renders  : %d", display.render_n)
    log.info("=" * 55)
    raw_lcd.clear()


if __name__ == "__main__":
    main()