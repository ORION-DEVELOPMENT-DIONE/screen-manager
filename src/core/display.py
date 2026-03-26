"""Display management"""
import logging
from PIL import Image
from config.constants import SCREEN_WIDTH, SCREEN_HEIGHT

class DisplayManager:
    def __init__(self, disp):
        self.disp = disp
        self._background_cache = {}

    def init(self):
        """Initialize display with optimizations"""
        self.disp.Init()
        self._optimize_performance()
        self.disp.clear()

    def _optimize_performance(self):
        """Apply performance optimizations"""
        try:
            self.disp.LCD_WriteReg(0x35)
            self.disp.LCD_WriteData_Byte(0x00)
            logging.info("Display optimizations applied")
        except Exception as e:
            logging.warning(f"Could not optimize display: {e}")

    def get_background_copy(self, theme):
        """Return a copy of the background, loading from disk only once per theme.

        First call per theme: opens the file, decodes JPEG, caches raw pixels.
        Every subsequent call (every scroll render): fast in-memory .copy() only.
        No disk I/O, no re-decode, no colour flicker between frames.
        """
        if theme.name not in self._background_cache:
            try:
                with Image.open(theme.background_path) as img:
                    self._background_cache[theme.name] = img.convert("RGB").copy()
                logging.info("Background cached for theme '%s'", theme.name)
            except Exception as e:
                logging.error(f"Error loading background: {e}")
                color = (0, 0, 0) if theme.name == "dark" else (255, 255, 255)
                self._background_cache[theme.name] = Image.new(
                    "RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), color=color
                )
        return self._background_cache[theme.name].copy()

    def invalidate_background_cache(self):
        """Force a fresh disk read on next render (call after theme switch)."""
        self._background_cache.clear()

    def show_image(self, image):
        """Display image"""
        try:
            self.disp.ShowImage(image)
        except Exception as e:
            logging.error(f"Display error: {e}")

    def clear(self):
        """Clear display"""
        self.disp.clear()

    def sleep(self):
        """Put display to sleep"""
        logging.info("Display sleep")
        self.disp.LCD_WriteReg(0x28)
        self.disp.LCD_WriteReg(0x10)

    def wake(self):
        """Wake display"""
        logging.info("Display wake")
        self.disp.LCD_WriteReg(0x11)
        import time
        time.sleep(0.12)
        self.disp.LCD_WriteReg(0x29)