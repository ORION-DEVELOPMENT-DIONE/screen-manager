"""
Touch handling — Orion Screen Manager
Enhanced with:
  - Direction-aware scroll lockout (MotionMask compatible)
  - Per-gesture-type debounce (scroll vs tap vs long-press)
  - Gesture profiling & statistics
  - Comprehensive logging for 24/7 operation
  - Clean state machine for WiFi async flows
"""
import time
import logging
from config.constants import (
    GESTURE_UP, GESTURE_DOWN, GESTURE_LEFT, GESTURE_RIGHT,
    GESTURE_TAP, GESTURE_LONG_PRESS,
    MENU_MAIN, MENU_WIFI, MENU_CONFIRM_NETWORK,
    STANDBY_TIMEOUT, GESTURE_DEBOUNCE, RENDER_THROTTLE,
)
from ui.wake_animation import play_boot_animation

log = logging.getLogger("orion.touch")

# ── Timing constants ──────────────────────────────────────────────────────────
# These override the simple GESTURE_DEBOUNCE for finer control.
#
# SCROLL_LOCKOUT_S: minimum gap between same-direction scroll accepts.
# The CST816S MotionMask fires every ~10ms while finger moves, so a single
# swipe produces ~15-30 events.  We need to absorb those duplicates but
# still allow rapid intentional flicks (separate finger lifts).
#
# 150ms = absorbs a single swipe's MotionMask burst (~150ms of events)
#         but lets you do ~6 scrolls/sec with quick flicks.
# The old 350ms felt sluggish because it also blocked the *next* swipe.
SCROLL_LOCKOUT_S   = 0.15   # fast — absorbs one swipe, allows rapid flicks
TAP_DEBOUNCE_S     = 0.18   # tap/double-tap suppression
LONGPRESS_COOLDOWN = 0.40   # post-long-press dead zone

_SCROLL_GESTURES = frozenset({GESTURE_UP, GESTURE_DOWN, GESTURE_LEFT, GESTURE_RIGHT})
_TAP_GESTURES    = frozenset({GESTURE_TAP, 0x0B})  # TAP + DOUBLE_TAP

GESTURE_NAMES = {
    GESTURE_UP:         "SWIPE_UP",
    GESTURE_DOWN:       "SWIPE_DOWN",
    GESTURE_LEFT:       "SWIPE_LEFT",
    GESTURE_RIGHT:      "SWIPE_RIGHT",
    GESTURE_TAP:        "TAP",
    GESTURE_LONG_PRESS: "LONG_PRESS",
    0x0B:               "DOUBLE_TAP",
}


class TouchHandler:
    """Main touch loop — runs entirely on the main thread.

    Enhancements over the original:
    1. **Direction-aware lockout** — scroll gestures in the same direction
       within SCROLL_LOCKOUT_S are suppressed (prevents MotionMask double-step).
       Different direction is always accepted immediately.
    2. **Separate debounce per type** — taps use TAP_DEBOUNCE_S, scrolls use
       SCROLL_LOCKOUT_S, long-press uses LONGPRESS_COOLDOWN.
    3. **Gesture statistics** — counts accepted/rejected gestures per type
       for diagnostics.
    4. **Clean async WiFi state machine** — tick() is called safely from the
       main thread; gestures are consumed-but-ignored during async ops.
    5. **All state transitions logged** for 24/7 traceability.
    """

    def __init__(self, touch, state, menu_handler):
        self.touch        = touch
        self.state        = state
        self.menu_handler = menu_handler

        # ── Debounce state ────────────────────────────────────────────────────
        self._last_accepted_gesture = None
        self._last_accepted_time    = 0.0
        self._post_longpress_until  = 0.0   # dead zone after long-press

        # ── Statistics ────────────────────────────────────────────────────────
        self._accepted_count: dict[int, int] = {}
        self._rejected_count: dict[int, int] = {}

    def init(self):
        self.touch.init()
        self.touch.Configure_Standby(timeout=5)

    def setup_callback(self, callback):
        self.touch.int_irq(9, callback)  # TP_INT = 9

    # ── Main loop ─────────────────────────────────────────────────────────────

    def handle_loop(self):
        """Main touch handling loop — runs entirely on the main thread."""
        log.info("Touch loop started")

        while True:
            current_time = time.time()
            gesture      = self.touch.Gestures

            # ── Standby ───────────────────────────────────────────────────────
            if self.state.is_standby:
                if gesture != 0:
                    self._wake_from_standby(current_time)
                time.sleep(0.08)
                continue

            # ── WiFi async state machine tick ─────────────────────────────────
            wifi_menu = self.menu_handler.wifi_menu
            if self.state.wifi_connecting or getattr(self.state, 'pairing_active', False):
                # Allow cancel gestures during pairing
                if gesture in [GESTURE_LEFT, GESTURE_LONG_PRESS]:
                    self.touch.Gestures = 0
                    self.menu_handler.wifi_menu.handle_gesture(gesture)
                    continue
                wifi_menu.tick()
                if gesture != 0:
                    self.touch.Gestures = 0  # discard non-cancel gestures
                time.sleep(0.15)
                continue

            # ── Scrolling animations ──────────────────────────────────────────
            self._handle_scrolling_animations(current_time)

            # ── Post-long-press dead zone ─────────────────────────────────────
            if current_time < self._post_longpress_until:
                if gesture != 0:
                    self.touch.Gestures = 0
                time.sleep(0.04)
                continue

            # ── Long press ────────────────────────────────────────────────────
            if gesture == GESTURE_LONG_PRESS:
                self._handle_long_press(current_time)
                continue

            # ── Regular gestures with direction-aware debounce ────────────────
            if gesture != 0:
                self._handle_gesture(gesture, current_time)

            # ── Standby check ─────────────────────────────────────────────────
            self._check_standby(current_time)

            time.sleep(0.02)  # 20ms poll — matches CST816S NorScanPer

    # ── Debounce logic ────────────────────────────────────────────────────────

    def _should_accept(self, gesture: int, now: float) -> bool:
        """Direction-aware debounce.

        - Scroll same direction within lockout → reject
        - Scroll different direction → always accept
        - Tap within TAP_DEBOUNCE_S of another tap → reject
        - Everything else → accept
        """
        elapsed = now - self._last_accepted_time
        same    = (gesture == self._last_accepted_gesture)

        is_scroll = gesture in _SCROLL_GESTURES
        is_tap    = gesture in _TAP_GESTURES

        if is_scroll and same and elapsed < SCROLL_LOCKOUT_S:
            self._rejected_count[gesture] = self._rejected_count.get(gesture, 0) + 1
            return False

        if is_tap and same and elapsed < TAP_DEBOUNCE_S:
            self._rejected_count[gesture] = self._rejected_count.get(gesture, 0) + 1
            return False

        return True

    def _accept(self, gesture: int, now: float):
        """Record acceptance for debounce tracking."""
        self._last_accepted_gesture = gesture
        self._last_accepted_time    = now
        self._accepted_count[gesture] = self._accepted_count.get(gesture, 0) + 1

        # Mark gesture timestamp for display latency profiling
        if hasattr(self.menu_handler, 'display'):
            self.menu_handler.display.mark_gesture()

    # ── Gesture handlers ──────────────────────────────────────────────────────

    def _handle_gesture(self, gesture: int, current_time: float):
        if not self._should_accept(gesture, current_time):
            self.touch.Gestures = 0
            return

        self.touch.Gestures = 0
        self._accept(gesture, current_time)

        name = GESTURE_NAMES.get(gesture, f"0x{gesture:02X}")
        log.info("Gesture: %s  menu=%d  selected=%d",
                 name, self.state.current_menu, self.state.selected_option)

        self.state.last_gesture       = gesture
        self.state.last_gesture_time  = current_time
        self.state.last_activity_time = current_time

        self.menu_handler.handle_gesture(gesture)

        # Clear any MotionMask events that arrived during render
        self.touch.Gestures = 0
        # NO sleep here — the lockout window handles debounce,
        # and the main loop's 40ms sleep provides the polling interval.

    def _handle_long_press(self, current_time: float):
        self.touch.Gestures = 0
        log.info("LONG_PRESS — returning to main menu")

        # Cancel ongoing WiFi operations cleanly
        if self.state.wifi_connecting or getattr(self.state, 'pairing_active', False):
            self.menu_handler.wifi_menu._reset_connect_state()
            self.state.pairing_active         = False
            self.state.in_saved_networks_mode = False
            self.state.saved_networks_list    = []
            log.info("Cancelled active WiFi operation")

        time.sleep(0.2)
        self.state.current_menu    = MENU_MAIN
        self.state.selected_option = 0
        self.state.current_page    = 0
        self.state.in_saved_networks_mode = False
        self.menu_handler.render_main_menu()

        self.state.last_gesture       = None
        self.state.last_gesture_time  = current_time
        self.state.last_activity_time = current_time

        # Post-long-press dead zone to prevent ghost taps
        self._post_longpress_until = current_time + LONGPRESS_COOLDOWN
        self._accept(GESTURE_LONG_PRESS, current_time)

    # ── Standby ───────────────────────────────────────────────────────────────
    
    def _wake_from_standby(self, current_time: float):
        log.info("Waking from standby")
        self.state.is_standby         = False
        self.state.last_activity_time = current_time
        self.touch.Stop_Sleep()
        self.touch.Set_Mode(0)

        # Push a black frame into the LCD buffer BEFORE turning
        # the display on — prevents the old menu from flashing
        from PIL import Image
        black = Image.new("RGB", (240, 240), (0, 0, 0))
        self.menu_handler.display.show_image(black)

        self.menu_handler.display.wake()
        self.touch.Gestures = 0

        # Quick wake animation — shows "WELCOME BACK"
        from ui.wake_animation import play_boot_animation
        play_boot_animation(self.menu_handler.display, quick=True)

        self.menu_handler.render_current_menu()
        self.state.last_gesture      = None
        self.state.last_gesture_time = current_time

    def _check_standby(self, current_time: float):
        if not self.state.is_standby and \
           (current_time - self.state.last_activity_time > STANDBY_TIMEOUT):
            log.info("Entering standby (idle %.0fs)",
                     current_time - self.state.last_activity_time)
            self.state.is_standby = True
            self.menu_handler.display.sleep()
            self.touch.Configure_Standby(timeout=5)
            self.touch.Gestures     = 0
            self.state.last_gesture = None

    # ── Scrolling animations ──────────────────────────────────────────────────

    def _handle_scrolling_animations(self, current_time: float):
        if self.touch.Gestures == 0:
            if current_time - self.state.last_render_time > RENDER_THROTTLE:
                if self.state.in_saved_networks_mode:
                    self.menu_handler.wifi_menu.render_saved_networks()
                    self.state.last_render_time = current_time
                elif self.state.current_menu == MENU_CONFIRM_NETWORK:
                    self.menu_handler.wifi_menu.render_network_confirmation()
                    self.state.last_render_time = current_time

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def gesture_stats(self) -> str:
        """Human-readable gesture statistics."""
        lines = ["Gesture Statistics:"]
        all_gestures = sorted(set(self._accepted_count) | set(self._rejected_count))
        for g in all_gestures:
            name = GESTURE_NAMES.get(g, f"0x{g:02X}")
            acc  = self._accepted_count.get(g, 0)
            rej  = self._rejected_count.get(g, 0)
            lines.append(f"  {name:15s}  accepted={acc:4d}  rejected={rej:4d}")
        return "\n".join(lines)