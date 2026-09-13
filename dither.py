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
#
# These are the actual output colours (not remapped to pure primaries): the
# panel's own ingestion pipeline nearest-matches each pixel to a hardware ink
# channel itself, so encoding the real muted colours here both dithers
# accurately and previews faithfully on a computer screen.
SPECTRA_E6_PALETTE = [
    (25, 30, 33),      # Black
    (232, 232, 232),   # White
    (239, 222, 68),    # Yellow
    (178, 19, 24),     # Red
    (33, 87, 186),     # Blue
    (18, 95, 32),      # Green
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

    Returns a 'P' mode (palette-indexed) image rather than converting back to
    RGB, so each pixel is stored as a 1-of-6 index -- this is what lets the
    PNG output stay small despite the high-frequency dithering noise.
    """
    palette_image = _build_palette_image(SPECTRA_E6_PALETTE)
    return image.convert("RGB").quantize(
        palette=palette_image, dither=Image.Dither.FLOYDSTEINBERG
    )
