"""Network pairing and configuration service

Thread-safety fix:
  - NEVER call self.renderer.render_message() — this was called from
    background threads and corrupted SPI display, causing blank screen + frozen UI.
  - Instead, write status strings to self.state.wifi_connect_status which the
    main loop reads via wifi_menu.tick() and renders safely on the main thread.
"""
import subprocess
import logging
import time

try:
    import requests
except ImportError:
    requests = None


class NetworkService:
    def __init__(self, renderer):
        self.renderer = renderer
        # Get state reference for thread-safe status updates
        self.state = getattr(renderer, 'state', None)

    def _update_status(self, msg):
        """Thread-safe status update — writes to state, never renders directly."""
        if self.state:
            self.state.wifi_connect_status = msg
        logging.info(f"Pairing status: {msg}")

    def _check_wifi_interface(self):
        """Check if WiFi interface is available and load if needed"""
        try:
            result = subprocess.run(['nmcli', 'device', 'status'],
                                  capture_output=True, text=True, timeout=5)

            if 'wifi' not in result.stdout:
                logging.warning("WiFi interface not found, attempting to load...")
                self._update_status("Loading WiFi\ninterface...")

                subprocess.run(['sudo', 'modprobe', '-r', 'rtw89_8852be'],
                             capture_output=True, timeout=10)
                time.sleep(2)

                subprocess.run(['sudo', 'modprobe', 'rtw89_8852be'],
                             capture_output=True, timeout=10)
                time.sleep(2)

                subprocess.run(['sudo', 'systemctl', 'restart', 'NetworkManager'],
                             capture_output=True, timeout=10)
                time.sleep(3)

                result = subprocess.run(['nmcli', 'device', 'status'],
                                      capture_output=True, text=True, timeout=5)

                if 'wifi' not in result.stdout:
                    return False

            return True
        except Exception as e:
            logging.error(f"Error checking WiFi interface: {e}")
            return False

    def ensure_orion_connection(self):
        """Connect to OrionSetup and wait for credentials.

        IMPORTANT: This runs in a background thread.
        It must NEVER call render_message() or show_image() directly.
        All UI updates go through self._update_status() → state flags → main loop.
        """
        try:
            # Check WiFi interface first
            if not self._check_wifi_interface():
                return (False, "WiFi interface\nnot available")

            # Phase 1: Connect to OrionSetup (with retry logic)
            max_retries = 2
            connected = False

            for attempt in range(max_retries):
                if attempt > 0:
                    self._update_status(f"Retrying...\n(Attempt {attempt + 1}/{max_retries})")
                    time.sleep(2)

                self._update_status("Checking\nconnection...")

                try:
                    result = subprocess.run(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                                          capture_output=True, text=True, timeout=5)

                    already_connected = False
                    for line in result.stdout.split('\n'):
                        if line.startswith('yes:') and 'OrionSetup' in line:
                            already_connected = True
                            break

                    if already_connected:
                        connected = True
                        break

                    # Scan for networks
                    self._update_status("Scanning\nnetworks...")
                    subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'],
                                 timeout=30, stderr=subprocess.DEVNULL)
                    time.sleep(3)  # Give scan time to complete

                    # List networks
                    result = subprocess.run(['nmcli', '-t', '-f', 'ssid', 'dev', 'wifi'],
                                          capture_output=True, text=True, timeout=5)

                    if 'OrionSetup' not in result.stdout:
                        logging.warning(f"OrionSetup not found in scan (attempt {attempt + 1})")
                        if attempt == max_retries - 1:
                            return (False, "Energy Meter\nnot found")
                        continue

                    # Try to connect
                    self._update_status("Connecting to\nOrionSetup...")

                    # Disconnect from current network first
                    subprocess.run(['sudo', 'nmcli', 'device', 'disconnect', 'wlan0'],
                                 capture_output=True, timeout=10)
                    time.sleep(1)

                    connect_result = subprocess.run([
                        'sudo', 'nmcli', 'dev', 'wifi', 'connect', 'OrionSetup',
                        'password', 'Orion2025'
                    ], capture_output=True, text=True, timeout=60)

                    if connect_result.returncode == 0:
                        connected = True
                        self._update_status("Connected to\nOrionSetup!")
                        time.sleep(2)
                        break
                    else:
                        logging.error(f"Connection failed (attempt {attempt + 1}): {connect_result.stderr}")
                        if attempt == max_retries - 1:
                            return (False, "Connection\nfailed")

                except subprocess.TimeoutExpired:
                    logging.error(f"Network command timeout (attempt {attempt + 1})")
                    if attempt == max_retries - 1:
                        return (False, "Connection\ntimeout")

            if not connected:
                return (False, "Could not connect\nto OrionSetup")

            # Phase 2: Wait for credentials with better timeout handling
            logging.info("Waiting for credentials from ESP32")
            if requests is None:
                return (False, "requests module\nnot available")

            poll_interval = 3
            poll_count = 0
            max_polls = 200  # 10 minutes max (200 * 3 seconds)

            while poll_count < max_polls:
                try:
                    # Check connection status
                    check_result = subprocess.run(
                        ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                        capture_output=True, text=True, timeout=2
                    )

                    still_connected = False
                    for line in check_result.stdout.split('\n'):
                        if line.startswith('yes:') and 'OrionSetup' in line:
                            still_connected = True
                            break

                    if not still_connected:
                        logging.warning("Disconnected from OrionSetup")
                        return (False, "Lost connection\nto OrionSetup")

                    # Poll for credentials
                    response = requests.get('http://192.168.4.1:8080/credentials', timeout=3)

                    if response.status_code == 200:
                        data = response.json()
                        ssid = data.get('ssid')
                        password = data.get('password')
                        validated = data.get('validated', False)

                        if ssid and validated:
                            logging.info(f"Received credentials: {ssid}")
                            self._update_status(f"Received:\n{ssid}")
                            time.sleep(1)

                            # Phase 3: Connect to new WiFi
                            subprocess.run(['sudo', 'nmcli', 'connection', 'delete', ssid],
                                         capture_output=True, check=False)
                            time.sleep(0.5)

                            self._update_status(f"Connecting to\n{ssid}...")

                            connect_result = subprocess.run([
                                'sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid,
                                'password', password
                            ], capture_output=True, text=True, timeout=60)

                            if connect_result.returncode == 0:
                                self._update_status(f"Connected to\n{ssid}!")
                                time.sleep(2)
                                return (True, "Pairing\ncomplete!")
                            else:
                                logging.error(f"Connection failed: {connect_result.stderr}")
                                subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect',
                                              'OrionSetup', 'password', 'Orion2025'],
                                             capture_output=True, timeout=30)
                                return (False, "Connection\nfailed")

                except subprocess.TimeoutExpired:
                    if poll_count % 20 == 0:
                        logging.debug(f"Still waiting for credentials ({poll_count * poll_interval}s elapsed)")
                except requests.exceptions.Timeout:
                    pass  # Expected — ESP32 hasn't served credentials yet
                except requests.exceptions.ConnectionError:
                    pass  # Expected — HTTP server not ready yet
                except Exception as e:
                    logging.error(f"Poll error: {e}")

                # Update status periodically
                poll_count += 1
                if poll_count % 5 == 0:
                    elapsed = poll_count * poll_interval
                    self._update_status(f"Waiting for\ncredentials...\n{elapsed}s")

                time.sleep(poll_interval)

            return (False, "Timeout waiting\nfor credentials")

        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            return (False, "Unexpected\nerror")