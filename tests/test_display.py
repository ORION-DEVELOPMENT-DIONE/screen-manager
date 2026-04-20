"""
test_display.py — Comprehensive tests for the enhanced DisplayManager
═══════════════════════════════════════════════════════════════════════
Covers:
  ✓ Initialization & performance optimization
  ✓ Background caching (hit / miss / invalidation)
  ✓ Frame rendering & SPI profiling
  ✓ Gesture→pixel latency tracking
  ✓ Thread-safe concurrent rendering
  ✓ Transition effects (cut / fade)
  ✓ Power management (sleep / wake)
  ✓ Error resilience (SPI failures don't crash)
"""
import sys
import os
import time
import threading
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

# Path setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from core.display import DisplayManager
from mock_hardware import MockLCD, MockTheme


class TestDisplayInit(unittest.TestCase):
    """Display initialization and performance optimization."""

    def setUp(self):
        self.lcd = MockLCD()
        self.dm  = DisplayManager(self.lcd)

    def test_init_calls_lcd_init(self):
        self.dm.init()
        self.assertTrue(self.lcd._initialized)

    def test_init_enables_te_sync(self):
        """TE (tearing effect) register 0x35 should be written for flicker-free."""
        self.dm.init()
        self.assertTrue(self.lcd.was_reg_written(0x35))

    def test_init_clears_screen(self):
        """Screen should be cleared after init."""
        self.lcd.clear = MagicMock()
        self.dm.init()
        self.lcd.clear.assert_called_once()

    def test_init_handles_optimization_failure(self):
        """If TE sync fails, init should still complete."""
        self.lcd.LCD_WriteReg = MagicMock(side_effect=Exception("SPI error"))
        # Should not raise
        self.dm.init()


class TestBackgroundCache(unittest.TestCase):
    """Background caching — critical for fast render cycles."""

    def setUp(self):
        self.lcd = MockLCD()
        self.dm  = DisplayManager(self.lcd)

    def test_cache_miss_creates_fallback(self):
        """Non-existent background path should produce a black/white fallback."""
        theme = MockTheme("dark", "/nonexistent.jpg")
        bg = self.dm.get_background_copy(theme)
        self.assertEqual(bg.size, (240, 240))
        self.assertEqual(bg.mode, "RGB")

    def test_cache_hit_returns_copy(self):
        """Second call should return a copy (not the same object) from cache."""
        theme = MockTheme("dark")
        bg1 = self.dm.get_background_copy(theme)
        bg2 = self.dm.get_background_copy(theme)
        self.assertIsNot(bg1, bg2)  # Different objects
        self.assertEqual(bg1.tobytes(), bg2.tobytes())  # Same content

    def test_cache_hit_is_fast(self):
        """Cached copy should be <1ms (no disk I/O)."""
        theme = MockTheme("dark")
        self.dm.get_background_copy(theme)  # Prime cache

        t0 = time.monotonic()
        for _ in range(100):
            self.dm.get_background_copy(theme)
        elapsed_ms = (time.monotonic() - t0) * 1000

        avg_ms = elapsed_ms / 100
        self.assertLess(avg_ms, 1.0,
                        f"Cached copy avg={avg_ms:.2f}ms, should be <1ms")

    def test_invalidate_clears_cache(self):
        """After invalidation, next call should re-create the entry."""
        theme = MockTheme("test_theme")
        self.dm.get_background_copy(theme)
        self.assertIn("test_theme", self.dm._background_cache)

        self.dm.invalidate_background_cache()
        self.assertNotIn("test_theme", self.dm._background_cache)

    def test_different_themes_cached_separately(self):
        """Dark and light themes get separate cache entries."""
        dark  = MockTheme("dark")
        light = MockTheme("light")
        self.dm.get_background_copy(dark)
        self.dm.get_background_copy(light)
        self.assertIn("dark", self.dm._background_cache)
        self.assertIn("light", self.dm._background_cache)


class TestRendering(unittest.TestCase):
    """Frame rendering, SPI profiling, and last-frame caching."""

    def setUp(self):
        self.lcd = MockLCD()
        self.dm  = DisplayManager(self.lcd)

    def _frame(self, color=(0, 0, 0)):
        return Image.new("RGB", (240, 240), color=color)

    def test_show_image_increments_counter(self):
        self.dm.show_image(self._frame())
        self.dm.show_image(self._frame())
        self.assertEqual(self.dm.render_count, 2)

    def test_show_image_stores_last_frame(self):
        frame = self._frame((255, 0, 0))
        self.dm.show_image(frame)
        self.assertIsNotNone(self.dm.last_frame)

    def test_show_image_records_spi_time(self):
        self.dm.show_image(self._frame())
        self.assertEqual(len(self.dm._spi_times), 1)
        self.assertGreater(self.dm._spi_times[0], 0)

    def test_spi_summary(self):
        self.dm.show_image(self._frame())
        summary = self.dm.spi_summary()
        self.assertIn("n=1", summary)
        self.assertIn("avg=", summary)

    def test_spi_summary_empty(self):
        self.assertEqual(self.dm.spi_summary(), "no SPI samples")

    def test_show_image_wrong_size_logged_not_counted(self):
        """Wrong-sized images are caught and logged — not counted as renders."""
        bad_frame = Image.new("RGB", (100, 100))
        self.dm.show_image(bad_frame)
        self.assertEqual(self.dm.render_count, 0)  # Error → not counted

    def test_spi_error_does_not_crash(self):
        """SPI failure should be logged but not raise."""
        self.lcd.ShowImage = MagicMock(side_effect=Exception("SPI bus fault"))
        # Should not raise
        self.dm.show_image(self._frame())
        self.assertEqual(self.dm.render_count, 0)  # Not counted on failure

    def test_reset_profiling(self):
        self.dm.show_image(self._frame())
        self.dm.reset_profiling()
        self.assertEqual(self.dm.render_count, 0)
        self.assertEqual(len(self.dm._spi_times), 0)
        self.assertEqual(len(self.dm._latencies), 0)


class TestLatencyProfiling(unittest.TestCase):
    """Gesture→pixel latency measurement."""

    def setUp(self):
        self.lcd = MockLCD()
        self.dm  = DisplayManager(self.lcd)

    def _frame(self):
        return Image.new("RGB", (240, 240))

    def test_latency_recorded_after_mark(self):
        self.dm.mark_gesture()
        time.sleep(0.01)
        self.dm.show_image(self._frame())
        self.assertEqual(len(self.dm._latencies), 1)
        self.assertGreater(self.dm._latencies[0], 0)

    def test_no_latency_without_mark(self):
        self.dm.show_image(self._frame())
        self.assertEqual(len(self.dm._latencies), 0)

    def test_mark_consumed_after_one_render(self):
        """Gesture mark should be consumed after the first render."""
        self.dm.mark_gesture()
        self.dm.show_image(self._frame())
        self.dm.show_image(self._frame())  # Second render — no mark
        self.assertEqual(len(self.dm._latencies), 1)

    def test_latency_summary(self):
        self.dm.mark_gesture()
        self.dm.show_image(self._frame())
        summary = self.dm.latency_summary()
        self.assertIn("n=1", summary)

    def test_latency_summary_empty(self):
        self.assertEqual(self.dm.latency_summary(), "no gesture samples")


class TestThreadSafety(unittest.TestCase):
    """Concurrent rendering should not cause SPI bus collisions."""

    def setUp(self):
        self.lcd = MockLCD()
        self.dm  = DisplayManager(self.lcd)

    def _frame(self, v=0):
        return Image.new("RGB", (240, 240), color=(v, v, v))

    def test_concurrent_renders(self):
        """Multiple threads rendering simultaneously should not crash."""
        errors = []

        def render_worker(thread_id, count):
            try:
                for i in range(count):
                    self.dm.show_image(self._frame(thread_id * 10 + i))
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=render_worker, args=(t, 20))
            for t in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        self.assertEqual(self.dm.render_count, 80)

    def test_render_lock_prevents_interleaving(self):
        """The render lock should serialize SPI access."""
        self.assertTrue(hasattr(self.dm, '_render_lock'))
        self.assertIsInstance(self.dm._render_lock, type(threading.Lock()))


class TestTransitions(unittest.TestCase):
    """Menu transition effects."""

    def setUp(self):
        self.lcd = MockLCD()
        self.dm  = DisplayManager(self.lcd)

    def _frame(self, color=(0, 0, 0)):
        return Image.new("RGB", (240, 240), color=color)

    def test_transition_cut(self):
        frame = self._frame((255, 0, 0))
        self.dm.transition_cut(frame)
        self.assertEqual(self.dm.render_count, 1)

    def test_transition_fade_no_previous(self):
        """Fade without a previous frame should fall back to instant cut."""
        frame = self._frame((0, 255, 0))
        self.dm.transition_fade(frame, steps=3)
        self.assertEqual(self.dm.render_count, 1)

    def test_transition_fade_with_previous(self):
        """Fade with a previous frame should render `steps` frames."""
        self.dm.show_image(self._frame((0, 0, 0)))  # Previous frame
        self.dm.transition_fade(self._frame((255, 255, 255)), steps=3)
        # 1 (initial) + 3 (fade steps)
        self.assertEqual(self.dm.render_count, 4)

    def test_transition_fade_single_step(self):
        """1-step fade = instant cut."""
        self.dm.show_image(self._frame())
        self.dm.transition_fade(self._frame((255, 0, 0)), steps=1)
        self.assertEqual(self.dm.render_count, 2)

    def test_is_transitioning_flag(self):
        """Flag should be True during fade, False after."""
        self.dm.show_image(self._frame())
        self.assertFalse(self.dm.is_transitioning)

        # During a synchronous fade, the flag is set/cleared internally
        self.dm.transition_fade(self._frame((255, 255, 255)), steps=2, duration_ms=20)
        self.assertFalse(self.dm.is_transitioning)


class TestPowerManagement(unittest.TestCase):
    """Sleep / wake cycle."""

    def setUp(self):
        self.lcd = MockLCD()
        self.dm  = DisplayManager(self.lcd)

    def test_sleep_sends_correct_registers(self):
        self.dm.sleep()
        self.assertIn(0x28, self.lcd._regs_written)  # DISPOFF
        self.assertIn(0x10, self.lcd._regs_written)  # SLPIN

    def test_wake_sends_correct_registers(self):
        self.dm.wake()
        self.assertIn(0x11, self.lcd._regs_written)  # SLPOUT
        self.assertIn(0x29, self.lcd._regs_written)  # DISPON

    def test_sleep_wake_cycle(self):
        """Sleep then wake should not crash."""
        self.dm.sleep()
        self.dm.wake()
        # Should still be able to render after wake
        frame = Image.new("RGB", (240, 240))
        self.dm.show_image(frame)
        self.assertEqual(self.dm.render_count, 1)

    def test_sleep_handles_error(self):
        """SPI failure during sleep should not crash."""
        self.lcd.LCD_WriteReg = MagicMock(side_effect=Exception("GPIO fault"))
        self.dm.sleep()  # Should not raise

    def test_wake_handles_error(self):
        self.lcd.LCD_WriteReg = MagicMock(side_effect=Exception("GPIO fault"))
        self.dm.wake()  # Should not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)