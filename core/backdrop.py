"""
Full-screen photographic backdrop via the kitty graphics protocol.

The earlier approach painted one blended colour per character cell. It was
portable, but a terminal is only ~190x50 cells, so the result was a 190x50
mosaic stretched over the whole window — and opaque panels covered it anyway,
so it only ever showed in the gaps.

Kitty can place a real image with a negative z-index, which puts it *behind* the
text layer. Every cell that does not set its own background colour then shows
the photo through it. So the panels stop being windows onto the image and become
what they should be: text floating above it.

Two consequences worth knowing.

Tone is baked into the pixels before transmission, not applied at composite
time, because terminal cells have no alpha channel. The photo keeps its own
colour and is only lifted toward white, which raises the shadows that dark text
needs to sit on. An earlier version instead flattened it toward the sandy base
tone, which read as a pink film over the whole terrace.

Everything must be transparent. A single widget with an opaque background
punches a hole in the backdrop, so the whole UI runs on `background:
transparent` and relies on borders and text colour for structure.
"""

import base64
import io
import math
import os
import sys
from functools import lru_cache
from pathlib import Path
import fcntl
import termios
import struct

from PIL import Image, ImageDraw

from core import frame as frame_art

def get_cell_aspect():
    try:
        # Try to get exact pixel dimensions from the terminal to avoid aspect ratio gaps
        res = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, struct.pack('HHHH', 0, 0, 0, 0))
        rows, cols, xpixels, ypixels = struct.unpack('HHHH', res)
        if cols > 0 and rows > 0 and xpixels > 0 and ypixels > 0:
            return (ypixels / rows) / (xpixels / cols)
    except Exception:
        pass
    return 2.0

CELL_ASPECT = get_cell_aspect()
CHUNK = 4096             # kitty requires the payload split into 4k base64 chunks

# The backdrop owns one image id so it can be deleted on its own. Deleting all
# images instead (`d=A`) would also wipe the portrait, which textual-image has
# placed through the same protocol — that is exactly what made her vanish.
IMAGE_ID = 7801
PORTRAIT_ID = 7802

# Negative z puts the placement under the text layer. -1 would be enough on
# paper, but the portrait is placed through the same protocol and its own z is
# textual-image's business, so leave a wide margin rather than sitting one step
# away from it. Kept well above INT32_MIN/2, below which kitty would draw the
# image beneath cell backgrounds too.
Z_INDEX = -1000

# She sits between the two: above the terrace, below the text. That ordering is
# what lets her run off the bottom of the screen with the input dock drawn over
# her legs, instead of being truncated by a widget boundary.
PORTRAIT_Z = -500

# Panel scrims sit just above the terrace and below her. They are separate
# placements rather than pixels burned into the backdrop, because panel geometry
# moves whenever the prompt grows — and re-sending the photograph for that cost
# seconds. A flat rounded rectangle is a few KB as PNG and re-places instantly.
SCRIM_Z = -900
SCRIM_BASE_ID = 7810
SCRIM_MAX = 16


# The prompt slab. CSS cannot deliver an opaque background here — TextArea paints
# from its own theme and the result never reached the terminal — so the slab is
# drawn as an image like everything else. Above her, below the text.
SLAB_ID = 7840
SLAB_Z = -100

# Past this width:height ratio a panel is "wide" and gets the wide frame. The
# square art stretched across a focus-mode console smears its edge runs.
WIDE_ASPECT = 1.9

_STATE = {
    "path": None,
    "base": (242, 226, 215),
    "blend": 1.0,
    "lift": 0.22,
    "scrim": 0.55,
    "size": None,
    "portrait": None,
    "scrims": None,
    "frame": None,
    "frame_wide": None,
    "slab": None,
}


def configure(image_path, base_colour, blend, lift=0.0, scrim=0.55,
              frame_path=None, wide_path=None):
    _STATE["path"] = str(Path(image_path))
    _STATE["base"] = tuple(base_colour)
    _STATE["blend"] = blend
    _STATE["lift"] = lift
    _STATE["scrim"] = scrim
    _STATE["size"] = None
    _STATE["portrait"] = None
    _STATE["scrims"] = None
    _STATE["frame"] = str(frame_path) if frame_path else None
    _STATE["frame_wide"] = str(wide_path) if wide_path else None
    _STATE["slab"] = None


def supported():
    """kitty announces itself in the environment; nothing else implements this."""
    return bool(os.environ.get("KITTY_WINDOW_ID")) or "kitty" in os.environ.get("TERM", "")


@lru_cache(maxsize=4)
def _prepare(cols, rows, _key=None):
    """
    Crop to the screen's true aspect and tone it. Photo only.

    Panel scrims used to be burned in here, which meant any layout change — even
    the prompt growing by one line — invalidated the whole 5.9MB image and paid
    a full rebuild and retransmit. They are separate placements now, so this is
    rebuilt only when the terminal itself is resized.
    """
    path, base, blend = _STATE["path"], _STATE["base"], _STATE["blend"]

    with Image.open(path) as source:
        image = source.convert("RGB")

        want = cols / (rows * CELL_ASPECT)
        have = image.width / image.height
        if have > want:
            new_w = int(image.height * want)
            left = (image.width - new_w) // 2
            image = image.crop((left, 0, left + new_w, image.height))
        elif have < want:
            new_h = int(image.width / want)
            top = (image.height - new_h) // 2
            image = image.crop((0, top, image.width, top + new_h))

        # A blend below 1.0 flattens the photo toward the base colour. That was
        # how text used to stay readable, at the cost of washing the image out;
        # at 1.0 it is a no-op and the photograph arrives untouched.
        if blend < 1.0:
            wash = Image.new("RGB", image.size, base)
            image = Image.blend(image, wash, 1.0 - blend)

        # Lift toward white rather than scaling brightness. Multiplying blows
        # out the sky — at 1.3x, 17% of the image clips to pure white — because
        # the highlights are already near the ceiling. Blending toward white
        # cannot exceed 255, so it lifts the shadows that dark text needs to sit
        # on while holding highlight detail, and unlike the old sandy wash it
        # adds no colour cast.
        lift = _STATE["lift"]
        if lift > 0.0:
            image = Image.blend(image, Image.new("RGB", image.size, (255, 255, 255)), lift)

        return image.tobytes(), image.width, image.height


def _write(payload):
    out = sys.__stdout__
    if out is None:
        return
    out.write(payload)
    out.flush()


def clear():
    """Delete only the backdrop placement, by id."""
    if supported():
        _write(f"\x1b_Ga=d,d=I,i={IMAGE_ID}\x1b\\")


def _place(image_id, payload, x, y, cols, rows, z, fmt=24, pixels=None,
           offset=None, placement=None):
    """
    Transmit and position one image, leaving the cursor where it was.

    `fmt` is a kitty pixel format: 24 for RGB, 32 for RGBA, 100 for a PNG file.
    The raw formats exist because PNG compression dominated everything else —
    encoding one backdrop cost ~1.6s, which is the entire reason toggling felt
    like the screen was being rebuilt. Raw pixels cost ~3ms. The payload is
    larger, but writing to a pty is memory-speed and kitty decodes nothing.
    Raw formats require the pixel dimensions, since there is no header to read
    them from.
    """
    encoded = base64.b64encode(payload).decode("ascii")
    chunks = [encoded[i:i + CHUNK] for i in range(0, len(encoded), CHUNK)]

    header = f"a=T,f={fmt},t=d,i={image_id},c={cols},r={rows},z={z},C=1,q=2"
    if placement is not None:
        # A named placement, so a later a=p with the same id replaces this
        # one instead of stacking another copy on top of it.
        header += f",p={placement}"
    if pixels:
        header += f",s={pixels[0]},v={pixels[1]}"
    if offset:
        # Pixel offset inside the starting cell. Placement is otherwise locked
        # to cell boundaries, and a scrim needs to land half a cell in, on the
        # border line rather than outside it.
        header += f",X={offset[0]},Y={offset[1]}"

    parts = [f"\x1b7\x1b[{y + 1};{x + 1}H"]
    for index, chunk in enumerate(chunks):
        more = 1 if index < len(chunks) - 1 else 0
        if index == 0:
            parts.append(f"\x1b_G{header},m={more};{chunk}\x1b\\")
        else:
            parts.append(f"\x1b_Gm={more};{chunk}\x1b\\")
    parts.append("\x1b8")
    _write("".join(parts))


@lru_cache(maxsize=4)
def _portrait_pixels(path, crop_rows=0, total_rows=1):
    """
    Decode her once to raw RGBA; f=32 keeps the alpha cutout.

    `crop_rows` trims that many rows' worth of pixels off the top. kitty cannot
    place an image at a negative row, so shifting her upward past the top of the
    screen means removing the part that would be off-screen and placing the
    remainder at row 0.
    """
    with Image.open(path) as source:
        image = source.convert("RGBA")
        if crop_rows > 0 and total_rows > 0:
            cut = min(image.height - 1, int(image.height * crop_rows / total_rows))
            image = image.crop((0, cut, image.width, image.height))
        return image.tobytes(), image.width, image.height


def clear_portrait():
    if supported():
        _write(f"\x1b_Ga=d,d=I,i={PORTRAIT_ID}\x1b\\")
    # Drop the cached placement too, or draw_portrait will believe she is still
    # on screen and skip redrawing her when the console collapses again.
    _STATE["portrait"] = None
    _STATE["scrims"] = None


def clear_scrims():
    if supported():
        for offset in range(SCRIM_MAX):
            _write(f"\x1b_Ga=d,d=I,i={SCRIM_BASE_ID + offset}\x1b\\")
    _STATE["scrims"] = None


# Nominal pixels per cell used to build a sheet. The value is arbitrary: kitty
# scales the PNG to the c x r cell box it is given, so only the proportions
# matter. Working in nominal units means the true cell size never has to be
# known, which is what the X/Y placement offset depended on.
SCRIM_CELL_W = 8
SCRIM_CELL_H = 16
SHEET_MAX_PX = 900   # cap on a generated sheet's longest side


@lru_cache(maxsize=32)
def _scrim_png(cols, rows, alpha):
    """
    A rounded translucent sheet, inset half a cell inside its own bounds.

    The inset lives in the image's alpha rather than in the placement. Kitty
    positions images on cell boundaries, and its X/Y in-cell offset did not move
    this placement, so every sheet sat half a cell up and to the left. Padding
    the sheet with transparency instead is exact, and scales with the image.
    """
    # Sheets are stretched to the cell box by kitty, so beyond a point extra
    # source resolution buys nothing and costs real time — a full-width prompt
    # strip would otherwise be built at 3008px across.
    scale = min(1.0, SHEET_MAX_PX / max(1, cols * SCRIM_CELL_W),
                SHEET_MAX_PX / max(1, rows * SCRIM_CELL_H))
    # Derive height from width rather than scaling both. Scaling each and
    # truncating drifts the nominal 1:2 cell — at focus-mode size it landed on
    # 4x9, an 11% aspect error that visibly squashed the ornament.
    cell_w = max(2, int(SCRIM_CELL_W * scale))
    cell_h = cell_w * (SCRIM_CELL_H // SCRIM_CELL_W)

    px_w, px_h = max(2, cols * cell_w), max(2, rows * cell_h)

    # Which frame: the wide art for a focus-mode console, the square one
    # otherwise. Stretching the square art that far smears its edge runs.
    art_path = _STATE.get("frame")
    if _STATE.get("frame_wide") and cols / max(1, rows * CELL_ASPECT) >= WIDE_ASPECT:
        art_path = _STATE["frame_wide"]

    # Inset the scrim to the ornament's inner edge so the tint stops where the
    # frame begins, rather than running underneath it.
    inset_x = inset_y = 0
    if art_path:
        corner = frame_art.corner_px(art_path, px_w, px_h)
        band = int(corner * frame_art.band_fraction(art_path))
        inset_x = min(band, px_w // 3)
        inset_y = min(band, px_h // 3)

    sheet = Image.new("RGBA", (px_w, px_h), (0, 0, 0, 0))
    ImageDraw.Draw(sheet).rounded_rectangle(
        [inset_x, inset_y, px_w - inset_x - 1, px_h - inset_y - 1],
        radius=max(2, cell_w * 0.9),
        fill=(255, 255, 255, alpha),
    )

    # The ornament rides on the same sheet as the scrim it frames, so a panel is
    # still a single placement and still moves in one `a=p`.
    if art_path:
        try:
            sheet.alpha_composite(frame_art.build(art_path, px_w, px_h))
        except Exception:
            pass

    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    return buffer.getvalue()


def ornament_cells(cols, rows):
    """
    How far the ornament reaches inside a panel, in cells (horizontal, vertical).

    Needed because the inset is computed in sheet pixels, and the sheet's cell
    size changes with the resolution cap — the same ~20px band is 2.6 cells on
    a collapsed panel but 4.8 on a focus-mode one. Callers use this to pad
    content clear of the frame instead of assuming a fixed margin.
    """
    if not _STATE.get("frame") or cols < 2 or rows < 2:
        return (0, 0)

    scale = min(1.0, SHEET_MAX_PX / max(1, cols * SCRIM_CELL_W),
                SHEET_MAX_PX / max(1, rows * SCRIM_CELL_H))
    cell_w = max(2, int(SCRIM_CELL_W * scale))
    cell_h = cell_w * (SCRIM_CELL_H // SCRIM_CELL_W)

    art = _STATE["frame"]
    if _STATE.get("frame_wide") and cols / max(1, rows * CELL_ASPECT) >= WIDE_ASPECT:
        art = _STATE["frame_wide"]

    corner = frame_art.corner_px(art, cols * cell_w, rows * cell_h)
    band = corner * frame_art.band_fraction(art)
    return (math.ceil(band / cell_w), math.ceil(band / cell_h))


def place_scrim(index, cx, cy, width, height):
    """
    Place a single sheet, without disturbing the others.

    Separate from draw_scrims so panels can be brought in one at a time — the
    startup cascade needs to add them individually rather than redrawing the
    whole set, which would flicker the ones already on screen.
    """
    if not supported() or width < 2 or height < 2 or index >= SCRIM_MAX:
        return
    png = _scrim_png(width, height, int(round(_STATE["scrim"] * 255)))
    _place(SCRIM_BASE_ID + index, png, cx, cy, width, height, SCRIM_Z,
           fmt=100, placement=1)


def draw_scrims(rects):
    """
    Place one translucent sheet per panel, covering exactly its cell region.

    """
    if not supported():
        return
    key = tuple(rects)
    if _STATE.get("scrims") == key:
        return

    clear_scrims()
    _STATE["scrims"] = key

    for index, (cx, cy, width, height) in enumerate(rects[:SCRIM_MAX]):
        place_scrim(index, cx, cy, width, height)


def clear_slab():
    if supported():
        _write(f"\x1b_Ga=d,d=I,i={SLAB_ID}\x1b\\")
    _STATE["slab"] = None


@lru_cache(maxsize=8)
def _slab_png(cols, rows, colour):
    px_w, px_h = cols * SCRIM_CELL_W, rows * SCRIM_CELL_H
    sheet = Image.new("RGBA", (px_w, px_h), (0, 0, 0, 0))
    ImageDraw.Draw(sheet).rounded_rectangle(
        [0, 0, px_w - 1, px_h - 1], radius=SCRIM_CELL_W, fill=tuple(colour) + (255,)
    )
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    return buffer.getvalue()


def draw_slab(x, y, cols, rows, colour=(13, 11, 18)):
    """An opaque panel behind the prompt, so it reads as a solid black bar."""
    if not supported() or cols < 2 or rows < 1:
        return
    key = (x, y, cols, rows, tuple(colour))
    if _STATE.get("slab") == key:
        return
    clear_slab()
    _STATE["slab"] = key
    _place(SLAB_ID, _slab_png(cols, rows, tuple(colour)), x, y, cols, rows,
           SLAB_Z, fmt=100, placement=1)


def draw_portrait(path, x, y, cols, rows, shift_rows=0):
    """
    Place the character as a raw kitty image rather than a Textual widget.

    A widget is clipped to its own region, so her legs were being cut off at the
    boundary above the input dock. Placed directly she can be sized past the
    bottom of the screen — kitty truncates at the edge — and the dock's text,
    which lives above her in z, simply draws over her.
    """
    if not supported() or cols <= 0 or rows <= 0:
        return
    # Shift her up by cropping whatever would sit above row 0, since kitty
    # has no negative placement. The horns are cut flat in the source, so
    # this pushes that edge off-screen instead of leaving it mid-frame.
    top = y - shift_rows
    crop_rows = max(0, -top)
    top = max(0, top)
    visible_rows = rows - crop_rows
    if visible_rows <= 0:
        return

    key = (str(path), top, x, cols, visible_rows, crop_rows)
    if _STATE.get("portrait") == key:
        return

    try:
        raw, px_w, px_h = _portrait_pixels(str(path), crop_rows, rows)
    except Exception:
        return

    clear_portrait()
    _STATE["portrait"] = key
    _place(PORTRAIT_ID, raw, x, top, cols, visible_rows, PORTRAIT_Z, fmt=32,
           pixels=(px_w, px_h))


def draw(cols, rows):
    """
    Place the backdrop behind the text layer.

    A deeply negative z puts it under both the text and the portrait. C=1 stops
    the cursor moving, which matters because Textual owns cursor position and
    would otherwise repaint from the wrong place.
    """
    if not supported() or not _STATE["path"] or cols <= 0 or rows <= 0:
        return
    key = (cols, rows)
    if _STATE["size"] == key:
        return

    tone = (_STATE["blend"], _STATE["lift"], _STATE["path"], _STATE["base"])
    try:
        raw, px_w, px_h = _prepare(cols, rows, tone)
    except Exception:
        return

    clear()
    _STATE["size"] = key

    _place(IMAGE_ID, raw, 0, 0, cols, rows, Z_INDEX, fmt=24, pixels=(px_w, px_h))
