"""Global application state"""
import time
from config.themes import THEMES


class AppState:
    def __init__(self):
        self.active_theme        = THEMES["dark"]
        self.current_menu        = 0
        self.selected_option     = 0
        self.current_page        = 0
        self.wifi_selected       = 0
        self.saved_networks_list = []
        self.saved_networks_selected = 0
        self.in_saved_networks_mode  = False
        self.in_wifi_qr_mode         = False
        self.network_to_connect      = None
        self.energy_metrics          = []
        self.energy_data             = {}
        self.chart_mode              = 0
        self.device_metrics_pages    = []
        self.last_gesture            = None
        self.last_gesture_time       = 0
        self.last_activity_time      = time.time()
        self.is_standby              = False
        self.scroll_offset           = 0
        self.last_scroll_time        = 0
        self.last_selected_network   = None
        self.last_render_time        = 0
        self.cached_current_ssid     = None
        self.last_ssid_check_time    = 0
        self.update_available        = False

        # Connectivity status (updated by ConnectivityService)
        self.wifi_connected  = False
        self.meter_paired    = False
        self.meter_last_seen = 0.0

        # Change-WiFi guide state
        self.in_change_wifi_guide = False
        self.change_wifi_step     = 0

        # ── Async WiFi connect flow ───────────────────────────────────────────
        # Background thread writes these; main loop reads and renders safely.
        self.wifi_connecting      = False   # True while nmcli is running
        self.wifi_connect_status  = ""      # live status string
        self.wifi_connect_result  = None    # (success, msg) when done
        self.wifi_result_shown_at = 0.0    # timestamp when result was first shown
        self.pairing_active       = False   # True during OrionSetup pairing flow

        # ── Pairing step-by-step UI ───────────────────────────────────────────
        # Written by NetworkService background thread, read by wifi_menu tick()
        self.pairing_step         = -1      # -1=inactive, 0=init, 1=scan, 2=portal, 3=connecting, 4=done
        self.pairing_step_label   = ""      # short label for current step
        self.pairing_ssid         = ""      # SSID being connected to (set in step 3)
        self.pairing_error        = ""      # error message if failed
        self.pairing_cancel       = False   # set True to abort background thread

state = AppState()