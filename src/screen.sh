#!/bin/bash
set -e
source /home/orangepi/venv/bin/activate
exec sudo python3 /home/orangepi/screen-manager/src/stdby3.py
