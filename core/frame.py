"""
Ornamental panel frames, nine-sliced.

The source art is a single fixed-aspect border. Stretching it straight onto a
panel would wreck it: panels range from very wide and short (a 34x9 status box)
to nearly square (a 58x25 console), so a plain resize squashes the corner
flourishes by different amounts on every panel.

Nine-slicing avoids that. The four corners are scaled uniformly and pasted at
fixed size, the four edge strips are stretched along one axis only, and the
middle is discarded. Ornament proportions survive at any panel shape, and the
straight runs simply get longer.
"""

from functools import lru_cache

from PIL import Image

# How much of the source is corner. Measured from the art: the flourishes run to
# roughly 300px in from each edge on a 1536x1024 sheet.
SRC_CORNER = 300

# A corner may never eat more than this fraction of the panel. The flourishes
# curve inward by design, so anything larger reaches past the border and sits
# on top of the first line of text.
MAX_CORNER_FRACTION = 0.16


@lru_cache(maxsize=4)
def _source(path):
    return Image.open(path).convert("RGBA")


@lru_cache(maxsize=4)
def band_fraction(path):
    """
    How deep the ornament runs from the edge, as a fraction of the corner slice.

    Measured from the art rather than guessed, because the two frames differ:
    the square one carries a ~10% band, the wide one ~11%. The scrim uses this
    to stop exactly at the ornament's inner edge instead of sliding underneath
    it.
    """
    src = _source(path)
    w, h = src.size
    alpha = src.split()[-1].load()
    cut = min(SRC_CORNER, w // 2, h // 2)

    depth = 0
    for y in range(h // 2):
        if alpha[w // 2, y] > 40:
            depth = y
    return min(1.0, (depth + 1) / max(1, cut))


def corner_px(path, width, height):
    """The corner size build() will use for this target, in pixels."""
    src = _source(path)
    cut = min(SRC_CORNER, src.size[0] // 2, src.size[1] // 2)
    return max(4, min(cut, int(min(width, height) * MAX_CORNER_FRACTION)))


@lru_cache(maxsize=48)
def build(path, width, height):
    """Return an RGBA frame of exactly (width, height) pixels."""
    src = _source(path)
    sw, sh = src.size
    cut = min(SRC_CORNER, sw // 2, sh // 2)

    # Target corner: uniform scale, so the flourish keeps its shape, capped so
    # opposite corners can never overlap on a small panel.
    limit = int(min(width, height) * MAX_CORNER_FRACTION)
    corner = max(4, min(cut, limit))

    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    boxes = {
        "tl": (0, 0, cut, cut),
        "tr": (sw - cut, 0, sw, cut),
        "bl": (0, sh - cut, cut, sh),
        "br": (sw - cut, sh - cut, sw, sh),
    }
    targets = {
        "tl": (0, 0),
        "tr": (width - corner, 0),
        "bl": (0, height - corner),
        "br": (width - corner, height - corner),
    }

    # Edges first, so corner detail lands on top of the seams.
    mid_w, mid_h = max(1, width - 2 * corner), max(1, height - 2 * corner)

    top = src.crop((cut, 0, sw - cut, cut)).resize((mid_w, corner), Image.LANCZOS)
    bottom = src.crop((cut, sh - cut, sw - cut, sh)).resize((mid_w, corner), Image.LANCZOS)
    left = src.crop((0, cut, cut, sh - cut)).resize((corner, mid_h), Image.LANCZOS)
    right = src.crop((sw - cut, cut, sw, sh - cut)).resize((corner, mid_h), Image.LANCZOS)

    out.paste(top, (corner, 0), top)
    out.paste(bottom, (corner, height - corner), bottom)
    out.paste(left, (0, corner), left)
    out.paste(right, (width - corner, corner), right)

    for key, box in boxes.items():
        piece = src.crop(box).resize((corner, corner), Image.LANCZOS)
        out.paste(piece, targets[key], piece)

    return out
