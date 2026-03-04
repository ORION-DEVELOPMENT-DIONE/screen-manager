"""Update menu"""
import time
from PIL import ImageDraw
from ui.renderer import BaseRenderer
from config.constants import *

class UpdateMenu(BaseRenderer):
    def __init__(self, display, state, update_checker):
        super().__init__(display, state)
        self.update_checker = update_checker
    
    def render(self):
        """Render update screen"""
        info = self.update_checker.get_update_info()
        
        # Check if update is actually available
        if not info['available']:
            self._render_no_updates(info)
            return
        
        image = self.get_background()
        draw = ImageDraw.Draw(image)
        
        # Title
        title = "Update Available"
        title_font = self.get_font(20)
        title_w = title_font.getlength(title)
        draw.text(((SCREEN_WIDTH - title_w) // 2, 20), title, 
                 fill=self.get_selected_color(), font=title_font)
        
        # Version info
        info_font = self.get_font(16)
        y = 60
        
        current_text = f"Current: {info['current']}"
        draw.text((20, y), current_text, fill=self.get_text_color(), font=info_font)
        y += 25
        
        latest_text = f"Latest:  {info['latest']}"
        draw.text((20, y), latest_text, fill=self.get_selected_color(), font=info_font)
        y += 40
        
        # Message
        msg = "Update now?"
        msg_w = self.get_font().getlength(msg)
        draw.text(((SCREEN_WIDTH - msg_w) // 2, y), msg, 
                 fill=self.get_text_color(), font=self.get_font())
        
        # Buttons
        self._draw_update_buttons(draw)
        
        self.display.show_image(image)
        del draw
        del image
    
    def _render_no_updates(self, info):
        """Render no updates available screen"""
        image = self.get_background()
        draw = ImageDraw.Draw(image)
        
        # Title
        title = "No Updates"
        title_font = self.get_font(20)
        title_w = title_font.getlength(title)
        draw.text(((SCREEN_WIDTH - title_w) // 2, 40), title, 
                 fill=self.get_text_color(), font=title_font)
        
        # Current version
        info_font = self.get_font(18)
        version_text = f"Version: {info['current']}"
        version_w = info_font.getlength(version_text)
        draw.text(((SCREEN_WIDTH - version_w) // 2, 90), version_text, 
                 fill=self.get_selected_color(), font=info_font)
        
        # Message
        msg_font = self.get_font(16)
        msg = "You're up to date!"
        msg_w = msg_font.getlength(msg)
        draw.text(((SCREEN_WIDTH - msg_w) // 2, 130), msg, 
                 fill=self.get_text_color(), font=msg_font)
        
        # Back button
        button_font = self.get_font(18)
        back_text = "← Back"
        back_w = button_font.getlength(back_text)
        draw.text(((SCREEN_WIDTH - back_w) // 2, 180), back_text, 
                 fill=self.get_selected_color(), font=button_font)
        
        self.display.show_image(image)
        del draw
        del image
    
    def _draw_update_buttons(self, draw):
        """Draw Update/Cancel buttons"""
        box_w, box_h = 90, 50
        box_y = 140
        spacing = 20
        total_width = 2 * box_w + spacing
        start_x = (SCREEN_WIDTH - total_width) // 2
        
        # CANCEL box
        draw.rectangle([start_x, box_y, start_x + box_w, box_y + box_h], 
                      outline=self.get_text_color(), width=2)
        cancel_text = "Cancel"
        cancel_font = self.get_font(18)
        cancel_w = cancel_font.getlength(cancel_text)
        draw.text((start_x + (box_w - cancel_w) // 2, box_y + 15), cancel_text, 
                 fill=self.get_text_color(), font=cancel_font)
        
        # UPDATE box
        draw.rectangle([start_x + box_w + spacing, box_y, 
                       start_x + 2 * box_w + spacing, box_y + box_h], 
                      outline=self.get_selected_color(), width=2)
        update_text = "Update"
        update_w = cancel_font.getlength(update_text)
        draw.text((start_x + box_w + spacing + (box_w - update_w) // 2, box_y + 15), 
                 update_text, fill=self.get_selected_color(), font=cancel_font)
    
    def handle_gesture(self, gesture, touch_device=None):
        """Handle update menu gestures"""
        info = self.update_checker.get_update_info()
        
        # If no updates, any gesture goes back
        if not info['available']:
            if gesture in [GESTURE_TAP, GESTURE_LONG_PRESS, GESTURE_LEFT]:
                return MENU_MAIN
            return None
        
        if gesture == GESTURE_LONG_PRESS:
            return MENU_MAIN
        
        if gesture == GESTURE_TAP and touch_device:
            touch_device.get_point()
            x, y = touch_device.X_point, touch_device.Y_point
            
            box_w, box_h = 90, 50
            box_y = 140
            spacing = 20
            start_x = (SCREEN_WIDTH - (2 * box_w + spacing)) // 2
            
            # CANCEL box
            if start_x <= x <= start_x + box_w and box_y <= y <= box_y + box_h:
                return MENU_MAIN
            
            # UPDATE box
            elif start_x + box_w + spacing <= x <= start_x + 2 * box_w + spacing and \
                 box_y <= y <= box_y + box_h:
                self._perform_update()
                return MENU_MAIN
        
        return None
    
    def _perform_update(self):
        """Execute the update"""
        self.render_message("Updating...\nPlease wait")
        time.sleep(1)
        
        success, message = self.update_checker.perform_update()
        
        self.render_message(message)
        time.sleep(3)
        
        if success:
            # Restart the service
            import os
            os.system("sudo systemctl restart screen.service")
