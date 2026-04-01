"""WiFi service for network operations"""
import subprocess
import logging
import time
import threading
from config.constants import SSID_CACHE_DURATION


class WiFiService:
    def __init__(self):
        self.cached_ssid     = None
        self.last_check_time = 0

    def get_current_ssid(self):
        current_time = time.time()
        if (self.cached_ssid is not None and
                (current_time - self.last_check_time) < SSID_CACHE_DURATION):
            return self.cached_ssid
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                capture_output=True, text=True, timeout=1
            )
            for line in result.stdout.split('\n'):
                if line.startswith('yes:'):
                    ssid = line.split(':', 1)[1].strip()
                    self.cached_ssid     = ssid
                    self.last_check_time = current_time
                    return ssid
            self.cached_ssid     = None
            self.last_check_time = current_time
            return None
        except subprocess.TimeoutExpired:
            return self.cached_ssid
        except Exception as e:
            logging.error(f"Error getting SSID: {e}")
            return self.cached_ssid

    def get_saved_networks(self):
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'NAME', 'connection', 'show'],
                capture_output=True, text=True, timeout=5
            )
            networks = [l.strip() for l in result.stdout.split('\n') if l.strip()]
            wifi_networks = []
            for network in networks:
                check = subprocess.run(
                    ['nmcli', '-t', '-f', 'connection.type', 'connection', 'show', network],
                    capture_output=True, text=True, timeout=2
                )
                if '802-11-wireless' in check.stdout:
                    wifi_networks.append(network)
            return wifi_networks
        except Exception as e:
            logging.error(f"Error getting saved networks: {e}")
            return []

    def connect_to_saved_network_async(self, network_name, state):
        """
        Non-blocking connect. Sets state flags that the main loop reads:
          state.wifi_connecting       = True while running
          state.wifi_connect_status   = current status string (shown on screen)
          state.wifi_connect_result   = (success, msg) when done, None while running
        """
        state.wifi_connecting     = True
        state.wifi_connect_status = f"Connecting to\n{network_name}..."
        state.wifi_connect_result = None

        def _worker():
            try:
                result_holder = [None]
                done          = threading.Event()

                def _nmcli():
                    try:
                        r = subprocess.run(
                            ['sudo', 'nmcli', 'connection', 'up', network_name],
                            capture_output=True, text=True, timeout=35
                        )
                        result_holder[0] = r
                    except subprocess.TimeoutExpired:
                        result_holder[0] = None
                    finally:
                        done.set()

                threading.Thread(target=_nmcli, daemon=True).start()

                dots = 0
                while not done.wait(timeout=3):
                    dots += 1
                    state.wifi_connect_status = (
                        f"Connecting{'.' * (dots % 4)}\n{network_name}"
                    )

                r = result_holder[0]
                if r is None:
                    state.wifi_connect_result = (False, "Timed out")
                elif r.returncode == 0:
                    self.cached_ssid = None
                    logging.info(f"Connected to {network_name}")
                    state.wifi_connect_result = (True, f"Connected!\n{network_name}")
                else:
                    err = r.stderr.strip().split('\n')[0] if r.stderr.strip() else ""
                    logging.error(f"Connection failed: {r.stderr}")
                    if "not found" in err.lower() or "could not be found" in err.lower():
                        state.wifi_connect_result = (False, "Network not\nin range")
                    elif "no secrets" in err.lower():
                        state.wifi_connect_result = (False, "Wrong\npassword")
                    else:
                        state.wifi_connect_result = (False, f"Failed\n{err[:35]}")

            except Exception as e:
                logging.error(f"Error connecting: {e}")
                state.wifi_connect_result = (False, f"Error\n{str(e)[:35]}")

        threading.Thread(target=_worker, daemon=True).start()

    def connect_to_saved_network(self, network_name):
        """Blocking connect — kept for backward compat."""
        try:
            result = subprocess.run(
                ['sudo', 'nmcli', 'connection', 'up', network_name],
                capture_output=True, text=True, timeout=35
            )
            if result.returncode == 0:
                logging.info(f"Connected to {network_name}")
                self.cached_ssid = None
                return True
            logging.error(f"Connection failed: {result.stderr}")
            return False
        except Exception as e:
            logging.error(f"Error connecting: {e}")
            return False

    def disconnect_wifi(self):
        try:
            current = self.get_current_ssid()
            if current:
                subprocess.run(
                    ['sudo', 'nmcli', 'connection', 'delete', current],
                    timeout=10
                )
                logging.info(f"Removed {current}")
                self.cached_ssid = None
                return True
        except Exception as e:
            logging.error(f"Error disconnecting: {e}")
        return False