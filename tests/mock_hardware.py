"""
Mock hardware modules for off-device testing.
Simulates LCD, Touch, SPI at the API level so all screen-manager
code can run on any machine (CI, dev laptop, etc).
"""
import time
import logging
import numpy as np
from PIL import Image

log = logging.getLogger("orion.mock")


# ── Mock LCD (GC9A01 240×240) ────────────────────────────────────────────────

class MockLCD:
    """Drop-in replacement for LCD_1inch28.LCD_1inch28."""

    def __init__(self):
        self.width  = 240
        self.height = 240
        self.np     = np
        self._initialized = False
        self._frame_count = 0
        self._last_image  = None
        self._regs_written: list[int] = []
        self._data_written: list[int] = []
        self.DC_PIN = 25
        self.SPI = MockSPI()

    def Init(self):
        self._initialized = True
        log.debug("MockLCD.Init()")

    def clear(self):
        log.debug("MockLCD.clear()")

    def LCD_WriteReg(self, reg):
        self._regs_written.append(reg)

    def LCD_WriteData_Byte(self, data):
        self._data_written.append(data)

    def digital_write(self, pin, value):
        pass  # GPIO stub

    def SetWindows(self, x0, y0, x1, y1):
        pass

    def ShowImage(self, image):
        """Accept a PIL Image exactly like the real driver."""
        imwidth, imheight = image.size
        if imwidth != self.width or imheight != self.height:
            raise ValueError(
                f"Image must be {self.width}x{self.height}, got {imwidth}x{imheight}"
            )
        self._frame_count += 1
        self._last_image = image.copy()
        # Simulate SPI transfer time (~18ms for 240×240 RGB565)
        time.sleep(0.001)

    def module_exit(self):
        log.debug("MockLCD.module_exit()")

    # ── Test helpers ──────────────────────────────────────────────────────────

    @property
    def frame_count(self):
        return self._frame_count

    @property
    def last_image(self):
        return self._last_image

    def was_reg_written(self, reg: int) -> bool:
        return reg in self._regs_written


class MockSPI:
    """Minimal SPI stub."""
    def __init__(self):
        self.bytes_sent = 0

    def writebytes2(self, data):
        if isinstance(data, (bytes, bytearray)):
            self.bytes_sent += len(data)
        else:
            self.bytes_sent += len(bytes(data))


# ── Mock Touch (CST816S) ─────────────────────────────────────────────────────

class MockTouch:
    """Drop-in replacement for Touch_1inch28.Touch_1inch28."""

    def __init__(self):
        self.Gestures = 0
        self.X_point  = 0
        self.Y_point  = 0
        self._mode    = 0
        self._irq_callback = None
        self._registers: dict[int, int] = {}
        self._initialized = False
        self._standby_configured = False
        self._sleep_stopped = False

    def init(self):
        self._initialized = True

    def Configure_Standby(self, timeout=5):
        self._standby_configured = True

    def Stop_Sleep(self):
        self._sleep_stopped = True

    def Set_Mode(self, mode):
        self._mode = mode

    def int_irq(self, pin, callback):
        self._irq_callback = callback

    def get_point(self):
        """Called before reading X_point, Y_point."""
        pass

    def Touch_Write_Byte(self, reg, val):
        self._registers[reg] = val

    def Touch_Read_Byte(self, reg):
        return self._registers.get(reg, 0)

    # ── Test helpers ──────────────────────────────────────────────────────────

    def simulate_gesture(self, gesture_code: int, x: int = 120, y: int = 120):
        """Simulate a gesture from the hardware IRQ."""
        self.Gestures = gesture_code
        self.X_point  = x
        self.Y_point  = y
        if self._irq_callback:
            self._irq_callback()

    def simulate_tap(self, x: int = 120, y: int = 120):
        self.simulate_gesture(0x05, x, y)

    def simulate_swipe_up(self):
        self.simulate_gesture(0x01)

    def simulate_swipe_down(self):
        self.simulate_gesture(0x02)

    def simulate_long_press(self):
        self.simulate_gesture(0x0C)


# ── Mock Theme ────────────────────────────────────────────────────────────────

class MockTheme:
    """Minimal theme object for testing DisplayManager.get_background_copy."""
    def __init__(self, name="dark", bg_path=None):
        self.name = name
        self.background_path = bg_path or "/nonexistent.jpg"