"""Overlay Unsplash photographer attribution onto the dithered image."""

from PIL import Image, ImageDraw, ImageFont

from dither import SPECTRA_E6_PALETTE

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE = 32
MARGIN = 24

BLACK = SPECTRA_E6_PALETTE[0]
WHITE = SPECTRA_E6_PALETTE[1]


def add_attribution(image: Image.Image, photographer_name: str) -> Image.Image:
    """Draw "By {photographer_name} on Unsplash" in the top-left corner.

    White text with a thin dark outline -- plain white would disappear
    against light regions of the dithered image. Unsplash's licence doesn't
    require attribution, but appreciates it.
    """
    text = f"By {photographer_name} on Unsplash"
    img = image.convert("RGB")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    x, y = MARGIN, MARGIN
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=BLACK)
    draw.text((x, y), text, font=font, fill=WHITE)
    return img
