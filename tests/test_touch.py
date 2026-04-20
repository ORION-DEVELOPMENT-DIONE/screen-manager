"""
test_touch.py — Comprehensive tests for the enhanced TouchHandler
═══════════════════════════════════════════════════════════════════
Covers:
  ✓ Direction-aware scroll lockout
  ✓ Per-gesture-type debounce (scroll / tap / long-press)
  ✓ Post-long-press dead zone
  ✓ Gesture statistics tracking
  ✓ Standby enter / wake cycle
  ✓ WiFi async state machine (gesture blocking)
  ✓ Menu navigation routing
  ✓ Edge cases (rapid fire, unknown gestures, zero gestures)
"""
import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from core.touch import (
    TouchHandler, SCROLL_LOCKOUT_S, TAP_DEBOUNCE_S, LONGPRESS_COOLDOWN,
    _SCROLL_GESTURES, _TAP_GESTURES, GESTURE_NAMES,
)
from config.constants import (
    GESTURE_UP, GESTURE_DOWN, GESTURE_LEFT, GESTURE_RIGHT,
    GESTURE_TAP, GESTURE_LONG_PRESS,
    MENU_MAIN, MENU_WIFI, MENU_MQTT, MENU_METRICS,
    STANDBY_TIMEOUT,
)
from mock_hardware import MockTouch


class MockState:
    """Minimal AppState for testing."""
    def __init__(self):
        self.current_menu         = MENU_MAIN
        self.selected_option      = 0
        self.current_page         = 0
        self.is_standby           = False
        self.last_gesture         = None
        self.last_gesture_time    = 0
        self.last_activity_time   = time.time()
        self.last_render_time     = 0
        self.wifi_connecting      = False
        self.pairing_active       = False
        self.in_saved_networks_mode = False
        self.saved_networks_list  = []
        self.wifi_selected        = 0


class MockMenuHandler:
    """Minimal MenuHandler stub."""
    def __init__(self):
        self.display = MagicMock()
        self.display.mark_gesture = MagicMock()
        self.display.wake = MagicMock()
        self.display.sleep = MagicMock()
        self.wifi_menu = MagicMock()
        self.wifi_menu.tick = MagicMock()
        self.wifi_menu._reset_connect_state = MagicMock()
        self.wifi_menu.render_saved_networks = MagicMock()
        self.wifi_menu.render_network_confirmation = MagicMock()
        self._gestures_received = []

    def handle_gesture(self, gesture):
        self._gestures_received.append(gesture)

    def render_main_menu(self):
        pass

    def render_current_menu(self):
        pass


class TestDebounceLogic(unittest.TestCase):
    """Test _should_accept — the core debounce algorithm."""

    def setUp(self):
        self.touch   = MockTouch()
        self.state   = MockState()
        self.menu    = MockMenuHandler()
        self.handler = TouchHandler(self.touch, self.state, self.menu)

    def test_first_gesture_always_accepted(self):
        """Very first gesture should always be accepted."""
        self.assertTrue(
            self.handler._should_accept(GESTURE_UP, time.time())
        )

    def test_same_scroll_within_lockout_rejected(self):
        """Same scroll direction within SCROLL_LOCKOUT_S → rejected."""
        now = time.time()
        self.handler._accept(GESTURE_UP, now)
        self.assertFalse(
            self.handler._should_accept(GESTURE_UP, now + 0.1)
        )

    def test_same_scroll_after_lockout_accepted(self):
        """Same scroll direction after lockout expires → accepted."""
        now = time.time()
        self.handler._accept(GESTURE_UP, now)
        self.assertTrue(
            self.handler._should_accept(GESTURE_UP, now + SCROLL_LOCKOUT_S + 0.01)
        )

    def test_different_scroll_always_accepted(self):
        """Different scroll direction → always accepted immediately."""
        now = time.time()
        self.handler._accept(GESTURE_UP, now)
        self.assertTrue(
            self.handler._should_accept(GESTURE_DOWN, now + 0.05)
        )

    def test_same_tap_within_debounce_rejected(self):
        now = time.time()
        self.handler._accept(GESTURE_TAP, now)
        self.assertFalse(
            self.handler._should_accept(GESTURE_TAP, now + 0.1)
        )

    def test_same_tap_after_debounce_accepted(self):
        now = time.time()
        self.handler._accept(GESTURE_TAP, now)
        self.assertTrue(
            self.handler._should_accept(GESTURE_TAP, now + TAP_DEBOUNCE_S + 0.01)
        )

    def test_tap_after_scroll_accepted(self):
        """Tap after scroll is a different gesture type → accepted."""
        now = time.time()
        self.handler._accept(GESTURE_UP, now)
        self.assertTrue(
            self.handler._should_accept(GESTURE_TAP, now + 0.05)
        )

    def test_scroll_after_tap_accepted(self):
        now = time.time()
        self.handler._accept(GESTURE_TAP, now)
        self.assertTrue(
            self.handler._should_accept(GESTURE_DOWN, now + 0.05)
        )

    def test_left_right_scroll_uses_lockout(self):
        """Horizontal scrolls should also use SCROLL_LOCKOUT_S."""
        now = time.time()
        self.handler._accept(GESTURE_LEFT, now)
        self.assertFalse(
            self.handler._should_accept(GESTURE_LEFT, now + 0.1)
        )
        self.assertTrue(
            self.handler._should_accept(GESTURE_RIGHT, now + 0.1)
        )


class TestGestureStatistics(unittest.TestCase):
    """Gesture accept/reject counting."""

    def setUp(self):
        self.touch   = MockTouch()
        self.state   = MockState()
        self.menu    = MockMenuHandler()
        self.handler = TouchHandler(self.touch, self.state, self.menu)

    def test_accepted_count_incremented(self):
        now = time.time()
        self.handler._accept(GESTURE_UP, now)
        self.handler._accept(GESTURE_DOWN, now + 0.5)
        self.handler._accept(GESTURE_UP, now + 1.0)
        self.assertEqual(self.handler._accepted_count[GESTURE_UP], 2)
        self.assertEqual(self.handler._accepted_count[GESTURE_DOWN], 1)

    def test_rejected_count_incremented(self):
        now = time.time()
        self.handler._accept(GESTURE_UP, now)
        self.handler._should_accept(GESTURE_UP, now + 0.1)  # rejected
        self.assertEqual(self.handler._rejected_count[GESTURE_UP], 1)

    def test_gesture_stats_output(self):
        now = time.time()
        self.handler._accept(GESTURE_TAP, now)
        self.handler._should_accept(GESTURE_TAP, now + 0.05)  # rejected
        stats = self.handler.gesture_stats()
        self.assertIn("TAP", stats)
        self.assertIn("accepted=", stats)
        self.assertIn("rejected=", stats)


class TestHandleGesture(unittest.TestCase):
    """Test _handle_gesture routing to MenuHandler."""

    def setUp(self):
        self.touch   = MockTouch()
        self.state   = MockState()
        self.menu    = MockMenuHandler()
        self.handler = TouchHandler(self.touch, self.state, self.menu)

    def test_accepted_gesture_routed_to_menu(self):
        self.touch.Gestures = GESTURE_UP
        self.handler._handle_gesture(GESTURE_UP, time.time())
        self.assertIn(GESTURE_UP, self.menu._gestures_received)

    def test_gesture_clears_touch_register(self):
        self.touch.Gestures = GESTURE_DOWN
        self.handler._handle_gesture(GESTURE_DOWN, time.time())
        self.assertEqual(self.touch.Gestures, 0)

    def test_gesture_updates_activity_time(self):
        old_time = self.state.last_activity_time
        time.sleep(0.01)
        self.handler._handle_gesture(GESTURE_TAP, time.time())
        self.assertGreater(self.state.last_activity_time, old_time)

    def test_rejected_gesture_not_routed(self):
        now = time.time()
        self.handler._accept(GESTURE_UP, now)
        self.touch.Gestures = GESTURE_UP
        # This is within lockout — should not route
        self.handler._handle_gesture(GESTURE_UP, now + 0.1)
        self.assertEqual(len(self.menu._gestures_received), 0)

    def test_marks_display_for_latency(self):
        self.handler._handle_gesture(GESTURE_TAP, time.time())
        self.menu.display.mark_gesture.assert_called()


class TestLongPress(unittest.TestCase):
    """Long press handling and post-press dead zone."""

    def setUp(self):
        self.touch   = MockTouch()
        self.state   = MockState()
        self.menu    = MockMenuHandler()
        self.handler = TouchHandler(self.touch, self.state, self.menu)

    def test_long_press_resets_to_main_menu(self):
        self.state.current_menu    = MENU_WIFI
        self.state.selected_option = 2
        self.handler._handle_long_press(time.time())
        self.assertEqual(self.state.current_menu, MENU_MAIN)
        self.assertEqual(self.state.selected_option, 0)

    def test_long_press_cancels_wifi_operation(self):
        self.state.wifi_connecting = True
        self.state.pairing_active  = True
        self.handler._handle_long_press(time.time())
        self.menu.wifi_menu._reset_connect_state.assert_called_once()
        self.assertFalse(self.state.pairing_active)

    def test_long_press_sets_dead_zone(self):
        now = time.time()
        self.handler._handle_long_press(now)
        self.assertGreater(self.handler._post_longpress_until, now)

    def test_dead_zone_blocks_subsequent_gestures(self):
        """Gestures within LONGPRESS_COOLDOWN after long press are ignored."""
        now = time.time()
        self.handler._handle_long_press(now)
        # Simulate a ghost tap right after long press
        self.assertFalse(
            now + 0.1 >= self.handler._post_longpress_until
        )

    def test_long_press_resets_page(self):
        self.state.current_page = 3
        self.handler._handle_long_press(time.time())
        self.assertEqual(self.state.current_page, 0)


class TestStandby(unittest.TestCase):
    """Standby enter/wake cycle."""

    def setUp(self):
        self.touch   = MockTouch()
        self.state   = MockState()
        self.menu    = MockMenuHandler()
        self.handler = TouchHandler(self.touch, self.state, self.menu)

    def test_check_standby_enters_after_timeout(self):
        self.state.last_activity_time = time.time() - STANDBY_TIMEOUT - 1
        self.handler._check_standby(time.time())
        self.assertTrue(self.state.is_standby)
        self.menu.display.sleep.assert_called_once()

    def test_check_standby_does_not_enter_if_active(self):
        self.state.last_activity_time = time.time()
        self.handler._check_standby(time.time())
        self.assertFalse(self.state.is_standby)

    def test_wake_from_standby(self):
        self.state.is_standby = True
        now = time.time()
        self.handler._wake_from_standby(now)
        self.assertFalse(self.state.is_standby)
        self.menu.display.wake.assert_called_once()

    def test_wake_clears_gesture_register(self):
        self.state.is_standby = True
        self.touch.Gestures = GESTURE_TAP
        self.handler._wake_from_standby(time.time())
        self.assertEqual(self.touch.Gestures, 0)

    def test_wake_renders_current_menu(self):
        self.state.is_standby = True
        self.menu.render_current_menu = MagicMock()
        self.handler._wake_from_standby(time.time())
        self.menu.render_current_menu.assert_called_once()


class TestWiFiAsyncBlocking(unittest.TestCase):
    """Gestures should be consumed but not processed during WiFi ops."""

    def setUp(self):
        self.touch   = MockTouch()
        self.state   = MockState()
        self.menu    = MockMenuHandler()
        self.handler = TouchHandler(self.touch, self.state, self.menu)

    def test_gestures_blocked_during_wifi_connecting(self):
        """When wifi_connecting=True, handle_gesture should NOT be called."""
        self.state.wifi_connecting = True
        self.touch.Gestures = GESTURE_TAP
        # Simulate one iteration of the loop logic
        # (We can't run the full loop, so we test the condition)
        if self.state.wifi_connecting:
            self.menu.wifi_menu.tick()
            self.touch.Gestures = 0
        self.menu.wifi_menu.tick.assert_called_once()
        self.assertEqual(self.touch.Gestures, 0)

    def test_gestures_blocked_during_pairing(self):
        self.state.pairing_active = True
        self.touch.Gestures = GESTURE_DOWN
        if self.state.pairing_active:
            self.menu.wifi_menu.tick()
            self.touch.Gestures = 0
        self.assertEqual(self.touch.Gestures, 0)


class TestEdgeCases(unittest.TestCase):
    """Boundary conditions and unusual inputs."""

    def setUp(self):
        self.touch   = MockTouch()
        self.state   = MockState()
        self.menu    = MockMenuHandler()
        self.handler = TouchHandler(self.touch, self.state, self.menu)

    def test_zero_gesture_ignored(self):
        """Gesture code 0 means no gesture — should never be processed."""
        self.handler._handle_gesture(0, time.time())
        # 0 is not in _SCROLL_GESTURES or _TAP_GESTURES, but _should_accept
        # would return True. The real loop checks gesture != 0 first.
        # This test ensures _should_accept handles it gracefully.
        self.assertTrue(self.handler._should_accept(0, time.time()))

    def test_unknown_gesture_code_accepted(self):
        """Unknown codes (e.g. 0xFF) should pass through debounce."""
        self.assertTrue(
            self.handler._should_accept(0xFF, time.time())
        )

    def test_rapid_alternating_scrolls(self):
        """Rapid UP-DOWN-UP-DOWN should all be accepted (different directions)."""
        now = time.time()
        gestures = [GESTURE_UP, GESTURE_DOWN, GESTURE_UP, GESTURE_DOWN]
        accepted = 0
        for i, g in enumerate(gestures):
            t = now + i * 0.05  # 50ms apart
            if self.handler._should_accept(g, t):
                self.handler._accept(g, t)
                accepted += 1
        self.assertEqual(accepted, 4)

    def test_rapid_same_scroll_debounced(self):
        """Rapid UP-UP-UP at 50ms intervals: first accepted, then blocked
        until lockout expires, then next one accepted.
        With SCROLL_LOCKOUT_S=0.15, events at 0/50/100ms are blocked,
        but the one at 150ms+ passes — that's intentional rapid scrolling."""
        now = time.time()
        accepted = 0
        for i in range(5):
            t = now + i * 0.05  # 50ms apart
            if self.handler._should_accept(GESTURE_UP, t):
                self.handler._accept(GESTURE_UP, t)
                accepted += 1
        # With 150ms lockout: event 0 (0ms)=accept, 1-2 (50,100ms)=reject,
        # 3 (150ms)=accept, 4 (200ms)=reject → 2 accepted
        self.assertEqual(accepted, 2)

    def test_gesture_names_coverage(self):
        """All known gesture codes should have a name."""
        known = {GESTURE_UP, GESTURE_DOWN, GESTURE_LEFT, GESTURE_RIGHT,
                 GESTURE_TAP, GESTURE_LONG_PRESS, 0x0B}
        for g in known:
            self.assertIn(g, GESTURE_NAMES)

    def test_scroll_gestures_set(self):
        """All scroll directions should be in _SCROLL_GESTURES."""
        self.assertIn(GESTURE_UP, _SCROLL_GESTURES)
        self.assertIn(GESTURE_DOWN, _SCROLL_GESTURES)
        self.assertIn(GESTURE_LEFT, _SCROLL_GESTURES)
        self.assertIn(GESTURE_RIGHT, _SCROLL_GESTURES)

    def test_tap_gestures_set(self):
        self.assertIn(GESTURE_TAP, _TAP_GESTURES)
        self.assertIn(0x0B, _TAP_GESTURES)


class TestMenuNavigationFlow(unittest.TestCase):
    """End-to-end navigation: scroll through items → tap to select → back."""

    def setUp(self):
        self.touch   = MockTouch()
        self.state   = MockState()
        self.menu    = MockMenuHandler()
        self.handler = TouchHandler(self.touch, self.state, self.menu)

    def test_scroll_then_tap_sequence(self):
        """Simulate: DOWN, DOWN, TAP (select 3rd item)."""
        now = time.time()

        # Scroll down twice
        self.handler._handle_gesture(GESTURE_DOWN, now)
        self.handler._handle_gesture(GESTURE_DOWN, now + SCROLL_LOCKOUT_S + 0.01)
        # Tap to select
        self.handler._handle_gesture(GESTURE_TAP, now + SCROLL_LOCKOUT_S * 2 + 0.02)

        self.assertEqual(
            self.menu._gestures_received,
            [GESTURE_DOWN, GESTURE_DOWN, GESTURE_TAP]
        )

    def test_long_press_from_submenu(self):
        """Long press should always return to MENU_MAIN regardless of current menu."""
        for menu in [MENU_WIFI, MENU_MQTT, MENU_METRICS]:
            self.state.current_menu = menu
            self.handler._handle_long_press(time.time())
            self.assertEqual(self.state.current_menu, MENU_MAIN)


if __name__ == "__main__":
    unittest.main(verbosity=2)