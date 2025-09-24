# /*****************************************************************************
# * | File        :	  epdconfig.py
# * | Author      :   Waveshare team
# * | Function    :   Hardware underlying interface
# * | Info        :
# *----------------
# * | This version:   V1.0
# * | Date        :   2019-06-21
# * | Info        :   
# ******************************************************************************
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documnetation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to  whom the Software is
# furished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS OR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import os
import sys
import time
from spidev import SpiDev
from smbus import SMBus
#import smbus
import logging
import numpy as np
import wiringpi
class OrangePi:
    def __init__(self, spi=None, spi_freq=40000000, rst=6, dc=25, bl=22, tp_int=9, tp_rst=4, bl_freq=1000):
        import wiringpi
        self.np = np
        self.RST_PIN = rst
        self.DC_PIN = dc
        self.BL_PIN = bl

        self.TP_INT = tp_int
        self.TP_RST = tp_rst

        self.X_point = self.Y_point = self.Gestures = 0
        
        self.SPEED = spi_freq
        self.BL_freq = bl_freq

        wiringpi.wiringPiSetup()
        # Initialize SPI
        self.SPI = spi
        self.SPI = SpiDev()   
        self.SPI.open(0,1)

        #self.SPI.max_speed_hz = self.SPEED
        self.I2C = SMBus(2)
        self.address = 0x15
   

    def digital_write(self, pin, value):
        wiringpi.pinMode(pin,1)
        wiringpi.digitalWrite(pin, value)

    def digital_read(self, pin):
        return wiringpi.digitalRead(pin)

    def int_irq(self, pin, Int_Callback):
        wiringpi.wiringPiISR(pin, wiringpi.INT_EDGE_FALLING, Int_Callback)

    def delay_ms(self, delaytime):
        time.sleep(delaytime / 1000.0)

 # Small delay to simulate a clock pulse, adjust as needed
    
    def spi_writebyte(self, data):
        self.SPI = SpiDev(0,1)
        if self.SPI is not None:   
           self.SPI.writebytes(data)
        self.SPI.close()
    

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
        wiringpi.softPwmWrite(self.BL_PIN , freq)

    def LCD_module_init(self):
        wiringpi.pinMode(self.RST_PIN, wiringpi.OUTPUT)
        wiringpi.pinMode(self.DC_PIN, wiringpi.OUTPUT)
        wiringpi.pinMode(self.BL_PIN, wiringpi.OUTPUT)

        print("PWM Initialization:")
        # Initialize PWM for backlight
        wiringpi.softPwmCreate(self.BL_PIN, 0, 100)
        wiringpi.softPwmWrite(self.BL_PIN, self.BL_freq)

        if self.SPI is not None:
            self.SPI = wiringpi.wiringPiSPISetupMode(0, 0, self.SPEED, 0)
        return 0
    
    
    def module_exit(self):
        
        logging.debug("spi end")
        if self.SPI is not None:
            self.SPI = None
        if self.I2C is not None:
            self.I2C = None

        logging.debug("gpio cleanup...")
        wiringpi.pinMode(self.RST_PIN, 1)
        wiringpi.pinMode(self.DC_PIN, 1)
        wiringpi.pinMode(self.TP_RST, 1)
        wiringpi.digitalWrite(self.RST_PIN, 1)
        wiringpi.digitalWrite(self.DC_PIN, 0)

        wiringpi.digitalWrite(self.TP_RST, 1)
        wiringpi.softPwmWrite(self.BL_PIN, 0)
        time.sleep(0.001)
        wiringpi.digitalWrite(self.BL_PIN, 1)

        # Optionally: wiringpi.cleanup() can be called, though it may not be necessary here



'''
if os.path.exists('/sys/bus/platform/drivers/gpiomem-bcm2835'):
    implementation = RaspberryPi()

for func in [x for x in dir(implementation) if not x.startswith('_')]:
    setattr(sys.modules[__name__], func, getattr(implementation, func))
'''

### END OF FILE ###
