import os
import sys
import time
from spidev import SpiDev
from smbus import SMBus
import logging
import numpy as np
import wiringpi

class OrangePi:
    def __init__(self, spi=None, spi_freq=40000000, rst=6, dc=25, bl=22, tp_int=9, tp_rst=4, bl_freq=1000):
        import wiringpi
        self.np = np
        self.RST_PIN = rst
        self.DC_PIN  = dc
        self.BL_PIN  = bl
        self.TP_INT  = tp_int
        self.TP_RST  = tp_rst

        self.X_point = self.Y_point = self.Gestures = 0

        self.SPEED   = spi_freq
        self.BL_freq = bl_freq

        wiringpi.wiringPiSetup()

        # Open SpiDev once, set speed immediately.
        # Original code left max_speed_hz commented out (kernel default ~375 kHz).
        # At 40 MHz a full 240x240 frame takes ~23ms instead of ~2500ms.
        self.SPI = SpiDev()
        self.SPI.open(0, 1)
        self.SPI.max_speed_hz = self.SPEED
        self.SPI.mode = 0

        self.I2C     = SMBus(2)
        self.address = 0x15

    def digital_write(self, pin, value):
        wiringpi.pinMode(pin, 1)
        wiringpi.digitalWrite(pin, value)

    def digital_read(self, pin):
        return wiringpi.digitalRead(pin)

    def int_irq(self, pin, Int_Callback):
        wiringpi.wiringPiISR(pin, wiringpi.INT_EDGE_FALLING, Int_Callback)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

    def spi_writebyte(self, data):
        # Reuse the persistent SpiDev handle — never re-open per call.
        self.SPI.writebytes2(data)

    def Touch_module_init(self):
        wiringpi.pinMode(self.TP_INT, wiringpi.INPUT)
        wiringpi.pinMode(self.TP_RST, wiringpi.OUTPUT)

    def i2c_write_byte(self, Addr, val):
        self.I2C.write_byte_data(self.address, Addr, val)

    def i2c_read_byte(self, Addr):
        return self.I2C.read_byte_data(self.address, Addr)

    def bl_DutyCycle(self, duty):
        wiringpi.softPwmCreate(self.BL_PIN, 0, 100)
        wiringpi.softPwmWrite(self.BL_PIN, duty)

    def bl_Frequency(self, freq):
        wiringpi.softPwmCreate(self.BL_PIN, 0, 100)
        wiringpi.softPwmWrite(self.BL_PIN, freq)

    def LCD_module_init(self):
        wiringpi.pinMode(self.RST_PIN, wiringpi.OUTPUT)
        wiringpi.pinMode(self.DC_PIN,  wiringpi.OUTPUT)
        wiringpi.pinMode(self.BL_PIN,  wiringpi.OUTPUT)

        # print("PWM Initialization:")
        wiringpi.softPwmCreate(self.BL_PIN, 0, 100)
        wiringpi.softPwmWrite(self.BL_PIN, self.BL_freq)

        # FIX: do NOT call wiringPiSPISetupMode here.
        # The original code did: self.SPI = wiringpi.wiringPiSPISetupMode(...)
        # wiringPiSPISetupMode returns an int (file descriptor), which overwrote
        # the SpiDev object, causing AttributeError on every subsequent SPI call.
        # SpiDev is already opened and configured in __init__ — nothing to do here.
        return 0

    def module_exit(self):
        logging.debug("spi end")
        if self.SPI is not None:
            self.SPI.close()
            self.SPI = None
        if self.I2C is not None:
            self.I2C = None

        logging.debug("gpio cleanup...")
        wiringpi.pinMode(self.RST_PIN, 1)
        wiringpi.pinMode(self.DC_PIN,  1)
        wiringpi.pinMode(self.TP_RST,  1)
        wiringpi.digitalWrite(self.RST_PIN, 1)
        wiringpi.digitalWrite(self.DC_PIN,  0)
        wiringpi.digitalWrite(self.TP_RST,  1)
        wiringpi.softPwmWrite(self.BL_PIN, 0)
        time.sleep(0.001)
        wiringpi.digitalWrite(self.BL_PIN, 1)

### END OF FILE ###