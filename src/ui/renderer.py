"""Base rendering functions"""
from PIL import Image, ImageDraw, ImageFont
from config.constants import *


class BaseRenderer:
    def __init__(self, display, state):
        self.display = display
        self.state   = state

    def get_background(self):
        return self.display.get_background_copy(self.state.active_theme)

    def get_font(self, size=24):
        """DejaVuSans — for all regular text."""
        return ImageFont.truetype("../Font/DejaVuSans.ttf", size)

    def get_emoji_font(self, size=24):
        """Symbola — for emoji characters.

        DejaVuSans has no emoji glyphs so emoji draws nothing.
        Symbola contains outline glyphs for the full Unicode emoji block
        and renders correctly at any size in Pillow.

        Usage:
            draw.text((x, y), "📶", font=self.get_emoji_font(24), fill=color)
            draw.text((x + 28, y), "Change WiFi", font=self.get_font(24), fill=color)
        """
        return ImageFont.truetype("../Font/Symbola.ttf", size)

    def draw_text_with_emoji(self, draw, pos, text, font_size=24, fill="white"):
        """Draw a string that may contain emoji mixed with regular text.

        Splits the string into emoji and non-emoji runs and uses the
        appropriate font for each segment.  Handles left-to-right layout.

        Example:
            self.draw_text_with_emoji(draw, (x, y), "📶 Change WiFi", 24, color)
        """
        import unicodedata
        x, y = pos
        regular_font = self.get_font(font_size)
        emoji_font   = self.get_emoji_font(font_size)

        for char in text:
            cat = unicodedata.category(char)
            # Emoji are in 'So' (Symbol, other) or have high codepoints
            is_emoji = (ord(char) > 0x2000 and cat in ('So', 'Sm', 'Sk', 'Mn'))
            font = emoji_font if is_emoji else regular_font
            draw.text((x, y), char, font=font, fill=fill)
            x += font.getlength(char)

    def get_text_color(self):
        return self.state.active_theme.text_color

    def get_selected_color(self):
        return self.state.active_theme.selected_color

    def wrap_text(self, text, font, max_width):
        lines = []
        words = text.split()
        current_line = ""
        for word in words:
            test_line = current_line + word + " "
            bbox = font.getbbox(test_line)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        if current_line:
            lines.append(current_line.strip())
        return lines

    def render_message(self, message, font_size=24):
        image = self.get_background()
        draw  = ImageDraw.Draw(image)

        if len(message) > 50:
            font = self.get_font(18)
        elif len(message) > 30:
            font = self.get_font(20)
        else:
            font = self.get_font(font_size)

        lines     = message.split('\n')
        all_lines = []
        for line in lines:
            if line.strip():
                all_lines.extend(self.wrap_text(line, font, MAX_WRAP_WIDTH))
            else:
                all_lines.append("")

        line_height  = font_size + 4
        total_height = len(all_lines) * line_height
        y_start      = max(30, (SCREEN_HEIGHT - total_height) // 2 - 10)

        for i, line in enumerate(all_lines):
            if line:
                line_w = font.getlength(line)
                x = (SCREEN_WIDTH - line_w) // 2
                y = y_start + i * line_height
                draw.text((x, y), line, fill=self.get_text_color(), font=font)

        self.display.show_image(image)
        del draw, image