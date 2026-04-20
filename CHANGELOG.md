# Orion Screen-Manager Changelog

## edd261a
### Bug Fixes
• Fixed MQTT reconnection loop on unstable networks
• Updated timestamp function to use device's current time.

### New Features
• Influxdb is now saving data to use it with Grafana Dashboard.
• Update description screen with vertical scrolling
• Energy Analyzer now shows 7-day trend

### Improvements
• Modularized screen-manager into src/ architecture
• Reduced SPI transfer time using tobytes()
