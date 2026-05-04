"""Network pairing and configuration service

Thread-safety fix:
  - NEVER call self.renderer.render_message() — this was called from
    background threads and corrupted SPI display, causing blank screen + frozen UI.
  - Instead, write status strings to self.state.wifi_connect_status which the
    main loop reads via wifi_menu.tick() and renders safely on the main thread.

Pairing step-by-step UI:
  - Writes pairing_step (0-4) + pairing_step_label for real-time screen updates

Important: During step 2 (portal/credential polling), we do NOT check nmcli
connection status. The ESP32 AP becomes flaky while it validates credentials
against the target WiFi (AP_STA mode). The HTTP poll itself handles true
disconnects via ConnectionError/Timeout exceptions.
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
        self.state = getattr(renderer, 'state', None)

    def _cancelled(self):
        """Check if user cancelled pairing."""
        return self.state and getattr(self.state, 'pairing_cancel', False)

    def _update_status(self, msg):
        """Thread-safe status update — writes to state, never renders directly."""
        if self.state:
            self.state.wifi_connect_status = msg
        logging.info(f"Pairing status: {msg}")

    def _set_pairing_step(self, step, label):
        """Thread-safe pairing step update for step-by-step UI."""
        if self.state:
            self.state.pairing_step = step
            self.state.pairing_step_label = label
        logging.info(f"Pairing step {step}: {label}")

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

    def _verify_orion_connection(self, retries=3, delay=2):
        """Verify OrionSetup connection is stable before proceeding."""
        for i in range(retries):
            if self._cancelled():
                return False
            time.sleep(delay)
            try:
                result = subprocess.run(
                    ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split('\n'):
                    if line.startswith('yes:') and 'OrionSetup' in line:
                        logging.info(f"OrionSetup connection verified (attempt {i+1})")
                        return True
            except Exception as e:
                logging.warning(f"Connection verify error: {e}")
        return False

    def ensure_orion_connection(self):
        """Connect to OrionSetup and wait for credentials.

        IMPORTANT: This runs in a background thread.
        It must NEVER call render_message() or show_image() directly.
        All UI updates go through self._update_status() → state flags → main loop.
        """
        try:
            # ── Step 0: Initialize ────────────────────────────────────────────
            self._set_pairing_step(0, "Checking WiFi")
            self._update_status("Initializing...")

            if not self._check_wifi_interface():
                self._set_pairing_step(4, "Failed")
                if self.state:
                    self.state.pairing_error = "WiFi interface\nnot available"
                return (False, "WiFi interface\nnot available")

            if self._cancelled():
                return (False, "Cancelled")

            # ── Step 1: Scan for OrionSetup ───────────────────────────────────
            self._set_pairing_step(1, "Scanning")
            max_retries = 3
            connected = False

            for attempt in range(max_retries):
                if self._cancelled():
                    return (False, "Cancelled")

                if attempt > 0:
                    self._update_status(f"Retrying...\n({attempt + 1}/{max_retries})")
                    time.sleep(3)

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
                        if self._verify_orion_connection(retries=2, delay=1):
                            connected = True
                            self._set_pairing_step(1, "AP connected")
                            break

                    # Scan for networks
                    self._update_status("Scanning\nnetworks...")
                    subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'],
                                 timeout=30, stderr=subprocess.DEVNULL)
                    time.sleep(5)

                    if self._cancelled():
                        return (False, "Cancelled")

                    # List networks
                    result = subprocess.run(['nmcli', '-t', '-f', 'ssid', 'dev', 'wifi'],
                                          capture_output=True, text=True, timeout=5)

                    if 'OrionSetup' not in result.stdout:
                        logging.warning(f"OrionSetup not found in scan (attempt {attempt + 1})")
                        if attempt == max_retries - 1:
                            self._set_pairing_step(4, "Not found")
                            if self.state:
                                self.state.pairing_error = "Energy Meter\nnot found"
                            return (False, "Energy Meter\nnot found")
                        continue

                    # Try to connect
                    self._set_pairing_step(1, "Connecting AP")
                    self._update_status("Connecting to\nOrionSetup...")

                    if self._cancelled():
                        return (False, "Cancelled")

                    connect_result = subprocess.run([
                        'sudo', 'nmcli', 'dev', 'wifi', 'connect', 'OrionSetup',
                        'password', 'Orion2025'
                    ], capture_output=True, text=True, timeout=60)

                    if connect_result.returncode == 0:
                        self._update_status("Verifying\nconnection...")
                        if self._verify_orion_connection(retries=3, delay=2):
                            connected = True
                            self._update_status("Connected to\nOrionSetup!")
                            break
                            
                        if self._cancelled():
                            return (False, "Cancelled")

                        else:
                            logging.warning(f"OrionSetup unstable (attempt {attempt + 1})")
                            if attempt == max_retries - 1:
                                self._set_pairing_step(4, "Unstable")
                                if self.state:
                                    self.state.pairing_error = "Connection\nunstable"
                                return (False, "Connection\nunstable")
                    else:
                        logging.error(f"Connection failed (attempt {attempt + 1}): {connect_result.stderr}")
                        if attempt == max_retries - 1:
                            self._set_pairing_step(4, "Failed")
                            if self.state:
                                self.state.pairing_error = "Connection\nfailed"
                            return (False, "Connection\nfailed")

                except subprocess.TimeoutExpired:
                    logging.error(f"Network command timeout (attempt {attempt + 1})")
                    if attempt == max_retries - 1:
                        self._set_pairing_step(4, "Timeout")
                        if self.state:
                            self.state.pairing_error = "Connection\ntimeout"
                        return (False, "Connection\ntimeout")

            if not connected:
                self._set_pairing_step(4, "Failed")
                if self.state:
                    self.state.pairing_error = "Could not connect\nto OrionSetup"
                return (False, "Could not connect\nto OrionSetup")

            # ── Step 2: Portal active — QR code screen ────────────────────────
            # IMPORTANT: Do NOT check nmcli connection status during this phase!
            # ESP32 runs in AP_STA mode and temporarily drops AP while validating
            # credentials against the target WiFi (~20s). The HTTP poll handles
            # true disconnects via ConnectionError/Timeout exceptions.
            self._set_pairing_step(2, "Open portal")
            self._update_status("Scan QR code\nto configure WiFi")

            logging.info("Waiting for credentials from ESP32")
            if requests is None:
                self._set_pairing_step(4, "Failed")
                if self.state:
                    self.state.pairing_error = "requests module\nnot available"
                return (False, "requests module\nnot available")

            poll_interval = 3
            poll_count = 0
            max_polls = 200  # 10 minutes max
            consecutive_conn_errors = 0
            max_conn_errors = 40  # 40 * 3s = 120s of total HTTP failure = truly gone

            while poll_count < max_polls:
                # Check if user cancelled
                if self.state and getattr(self.state, 'pairing_cancel', False):
                    logging.info("Pairing cancelled by user")
                    self._set_pairing_step(4, "Cancelled")
                    if self.state:
                        self.state.pairing_error = "Cancelled"
                    return (False, "Cancelled")
                try:
                    # Poll for credentials — NO nmcli check here
                    response = requests.get('http://192.168.4.1:8080/credentials', timeout=5)

                    # Got a response — connection is alive, reset error count
                    consecutive_conn_errors = 0

                    if response.status_code == 200:
                        data = response.json()
                        ssid = data.get('ssid')
                        password = data.get('password')
                        validated = data.get('validated', False)

                        if ssid and validated:
                            logging.info(f"Received credentials: {ssid}")

                            # ── Step 3: Connecting to new WiFi ────────────────
                            self._set_pairing_step(3, "Connecting")
                            if self.state:
                                self.state.pairing_ssid = ssid
                            self._update_status(f"Received:\n{ssid}")
                            time.sleep(1)

                            self._update_status(f"Connecting to\n{ssid}...")

                            connect_result = subprocess.run([
                                'sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid,
                                'password', password
                            ], capture_output=True, text=True, timeout=60)

                            if connect_result.returncode == 0:
                                self._update_status(f"Connected to\n{ssid}!")
                                self._set_pairing_step(4, "Complete")
                                if self.state:
                                    self.state.pairing_error = ""
                                time.sleep(2)
                                return (True, "Pairing\ncomplete!")
                            else:
                                logging.error(f"Connection failed: {connect_result.stderr}")
                                self._set_pairing_step(4, "Failed")
                                if self.state:
                                    self.state.pairing_error = f"Failed to join\n{ssid}"
                                subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect',
                                              'OrionSetup', 'password', 'Orion2025'],
                                             capture_output=True, timeout=30)
                                return (False, "Connection\nfailed")

                except subprocess.TimeoutExpired:
                    if poll_count % 20 == 0:
                        logging.debug(f"Still waiting for credentials ({poll_count * poll_interval}s elapsed)")
                except requests.exceptions.Timeout:
                    # Expected — ESP32 busy validating, AP temporarily down
                    consecutive_conn_errors += 1
                    if poll_count % 10 == 0:
                        logging.debug(f"HTTP timeout (conn_errors={consecutive_conn_errors})")
                except requests.exceptions.ConnectionError:
                    # Expected during ESP32 validation phase (~20s)
                    consecutive_conn_errors += 1
                    if poll_count % 10 == 0:
                        logging.debug(f"HTTP connection error (conn_errors={consecutive_conn_errors})")
                except Exception as e:
                    logging.error(f"Poll error: {e}")
                    consecutive_conn_errors += 1

                # Only give up if HTTP has been failing for a LONG time
                if consecutive_conn_errors >= max_conn_errors:
                    logging.error(f"Lost connection to ESP32 ({consecutive_conn_errors} consecutive errors)")
                    self._set_pairing_step(4, "Disconnected")
                    if self.state:
                        self.state.pairing_error = "Lost connection\nto OrionSetup"
                    return (False, "Lost connection\nto OrionSetup")

                # Update status periodically
                poll_count += 1
                if poll_count % 5 == 0:
                    elapsed = poll_count * poll_interval
                    self._update_status(f"Waiting for\ncredentials...\n{elapsed}s")

                time.sleep(poll_interval)

            self._set_pairing_step(4, "Timeout")
            if self.state:
                self.state.pairing_error = "Timeout waiting\nfor credentials"
            return (False, "Timeout waiting\nfor credentials")

        except Exception as e:
            logging.error(f"Error: {e}", exc_info=True)
            self._set_pairing_step(4, "Error")
            if self.state:
                self.state.pairing_error = "Unexpected\nerror"
            return (False, "Unexpected\nerror")