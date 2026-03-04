"""Main menu rendering and handling"""
import time
from PIL import ImageDraw
from ui.renderer import BaseRenderer
from config.constants import *
from config.themes import TOGGLE_THEME_EMOJI, THEMES

class MainMenu(BaseRenderer):
    def __init__(self, display, state):
        super().__init__(display, state)
        self.base_items = ["Energy", "Device", "WiFi Setup", "Update", "Shutdown"]
    
    def get_items(self):
        """Get menu items with update notification"""
        items = []
        for item in self.base_items:
            if item == "Update" and self.state.update_available:
                items.append("(1) Update")  # Add notification badge
            else:
                items.append(item)
        return items
    
    def render(self):
        """Render main menu"""
        image = self.get_background()
        draw = ImageDraw.Draw(image)
        
        items = self.get_items()
        
        # Calculate vertical spacing to center all items
        item_height = 35  # Height per item
        total_height = len(items) * item_height
        y_start = (SCREEN_HEIGHT - total_height) // 2
        
        for i, item in enumerate(items):
            is_selected = (i == self.state.selected_option)
            
            # Color logic
            if item.startswith("(1) Update"):
                # Update item with notification - orange
                color = "orange" if not is_selected else self.get_selected_color()
            else:
                # Normal items
                color = self.get_selected_color() if is_selected else self.get_text_color()
            
            # Add selection arrow
            prefix = "➤ " if is_selected else "  "
            display_text = prefix + item
            
            # Center text
            text_w = self.get_font().getlength(display_text)
            x = (SCREEN_WIDTH - text_w) // 2
            y = y_start + i * item_height
            
            draw.text((x, y), display_text, fill=color, font=self.get_font())
        
        # Theme toggle at bottom
        emoji_w = self.get_font().getlength(TOGGLE_THEME_EMOJI)
        draw.text(((SCREEN_WIDTH - emoji_w) // 2, SCREEN_HEIGHT - 35), 
                 TOGGLE_THEME_EMOJI, fill=self.get_selected_color(), font=self.get_font())
        
        self.display.show_image(image)
        del draw
        del image
    
    def handle_gesture(self, gesture, touch_device=None):
        """Handle main menu gestures"""
        items = self.get_items()
        
        if gesture == GESTURE_UP:
            self.state.selected_option = (self.state.selected_option - 1) % len(items)
            self.render()
        elif gesture == GESTURE_DOWN:
            self.state.selected_option = (self.state.selected_option + 1) % len(items)
            self.render()
        elif gesture == GESTURE_TAP:
            return self._handle_selection(touch_device)
        
        return None
    
    def _handle_selection(self, touch_device):
        """Handle menu selection"""
        # Check for theme toggle
        if touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            
            # Theme toggle area (bottom center)
            emoji_y_range = (205, 235)
            emoji_w = self.get_font().getlength(TOGGLE_THEME_EMOJI)
            emoji_x_range = ((SCREEN_WIDTH - emoji_w) // 2 - 10, (SCREEN_WIDTH + emoji_w) // 2 + 10)

            if emoji_y_range[0] <= y <= emoji_y_range[1] and emoji_x_range[0] <= x <= emoji_x_range[1]:
                # Toggle theme
                self.state.active_theme = THEMES["light"] if self.state.active_theme.name == "dark" else THEMES["dark"]
                self.render()
                time.sleep(0.2)
                return None
        
        time.sleep(0.1)
        
        # Map selection to menu
        # Items: ["Energy", "Device", "WiFi Setup", "Update", "Shutdown"]
        menu_map = {
            0: MENU_MQTT,       # Energy
            1: MENU_METRICS,    # Device
            2: MENU_WIFI,       # WiFi Setup
            3: MENU_UPDATE,     # Update
            4: MENU_CONFIRM_SHUTDOWN  # Shutdown
        }
        
        return menu_map.get(self.state.selected_option)