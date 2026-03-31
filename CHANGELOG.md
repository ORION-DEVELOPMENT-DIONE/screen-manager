# Orion Screen-Manager Changelog

## edd261a
### Bug Fixes
• Fixed MQTT reconnection loop on unstable networks
• Resolved NVS calibration key mismatch causing measurement error

### New Features
• Update description screen with vertical scrolling
• Energy Analyzer now shows 7-day trend

### Improvements
• Modularized screen-manager into src/ architecture
• Reduced SPI transfer time using tobytes()
