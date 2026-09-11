"""Floyd-Steinberg dithering to the E Ink Spectra 6 (E6) six-colour palette."""

from PIL import Image

# E Ink publishes no numeric colour spec for Spectra 6; these are community
# measurements of how the panel actually renders each colour (desaturated
# compared to pure primaries), sourced from a dithering tool built for the
# same 13.3" Spectra 6 panel this project targets:
# https://gist.github.com/quark-zju/e488eb206ba66925dc23692170ba49f9
# A second independent source (a JS dithering library for e-paper displays,
# github.com/Utzel-Butzel/epdoptimize) measured comparable but not identical
# muted values -- panels vary by batch and viewing light, so treat this as a
# good approximation rather than ground truth. For best fidelity, replace
# these with values measured from your own physical panel.
SPECTRA_E6_PERCEPTUAL_PALETTE = [
    (25, 30, 33),      # Black
    (232, 232, 232),   # White
    (239, 222, 68),    # Yellow
    (178, 19, 24),     # Red
    (33, 87, 186),     # Blue
    (18, 95, 32),      # Green
]

# The pure-primary codes the panel's driver/firmware expects in the output
# file -- drivers typically nearest-match each pixel against a hardcoded
# pure-primary table to pick the hardware ink channel unambiguously, so the
# *encoded* pixel values must be these, even though the *matching* decision
# above is made against the muted colours the panel actually displays.
SPECTRA_E6_DEVICE_PALETTE = [
    (0, 0, 0),        # Black
    (255, 255, 255),  # White
    (255, 255, 0),    # Yellow
    (255, 0, 0),      # Red
    (0, 0, 255),       # Blue
    (0, 255, 0),       # Green
]


def _build_palette_image(colors: list[tuple[int, int, int]]) -> Image.Image:
    """Build a 1x1 'P' mode image whose palette is exactly `colors`.

    Image.quantize(palette=...) matches every pixel against the colours
    present in this palette image only, so padding entries are set to repeat
    the last real colour and are never selected as nearest neighbours ahead
    of a real one at equal distance.
    """
    pal_img = Image.new("P", (1, 1))
    flat: list[int] = []
    for c in colors:
        flat.extend(c)
    flat.extend(list(colors[-1]) * (256 - len(colors)))
    pal_img.putpalette(flat)
    return pal_img


def dither_to_spectra_e6(image: Image.Image) -> Image.Image:
    """Floyd-Steinberg dither an RGB image down to the Spectra E6 palette.

    Matches and diffuses error against the perceptual (muted) palette, so
    the colour picked for each pixel is the one the panel will actually
    reproduce most closely -- then swaps in the device pure-primary colours
    for the same pixel indices, so the output file encodes exactly what the
    panel's driver expects while the dithering decision stays accurate.

    Returns a 'P' mode (palette-indexed) image rather than converting back to
    RGB, so each pixel is stored as a 1-of-6 index -- this is what lets the
    PNG output stay small despite the high-frequency dithering noise.
    """
    perceptual_palette_image = _build_palette_image(SPECTRA_E6_PERCEPTUAL_PALETTE)
    quantized = image.convert("RGB").quantize(
        palette=perceptual_palette_image, dither=Image.Dither.FLOYDSTEINBERG
    )

    device_flat: list[int] = []
    for c in SPECTRA_E6_DEVICE_PALETTE:
        device_flat.extend(c)
    device_flat.extend(list(SPECTRA_E6_DEVICE_PALETTE[-1]) * (256 - len(SPECTRA_E6_DEVICE_PALETTE)))
    quantized.putpalette(device_flat)
    return quantized
