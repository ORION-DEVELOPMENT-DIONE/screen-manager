"""Menu modules"""
from .main_menu import MainMenu
from .wifi_menu import WiFiMenu
from .energy_menu import EnergyMenu
from .device_menu import DeviceMenu
from .confirmation import ConfirmationMenu
from .update_menu import UpdateMenu

__all__ = [
    'MainMenu',
    'WiFiMenu', 
    'EnergyMenu',
    'DeviceMenu',
    'ConfirmationMenu',
    'UpdateMenu'
    'DashboardMenu'
]