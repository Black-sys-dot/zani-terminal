import os
from PIL import Image


# ==========================================================
# ANSI IMAGE RENDERER (YOUR SCRIPT — UNTOUCHED)
# ==========================================================

def render_logo(image_path, width=60):
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"Error: {e}")
        return

    original_width, original_height = img.size
    aspect_ratio = original_height / original_width
    height = int(width * aspect_ratio)
    img = img.resize((width, height))

    reset = "\033[0m"

    for y in range(0, height - 1, 2):
        line = ""
        for x in range(width):
            top_rgb = img.getpixel((x, y))
            bottom_rgb = img.getpixel((x, y + 1))

            line += f"\033[38;2;{top_rgb[0]};{top_rgb[1]};{top_rgb[2]}m"
            line += f"\033[48;2;{bottom_rgb[0]};{bottom_rgb[1]};{bottom_rgb[2]}m"
            line += "▀"

        print(line + reset)


# ==========================================================
# IMAGE REGISTRY
# ==========================================================

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
ASSETS = os.path.join(BASE_DIR, "assets")


IMAGES = {
    "init": os.path.join(ASSETS, "zani_init.png"),
    "threshold": os.path.join(ASSETS, "zani_threshold.png"),
    "cache": os.path.join(ASSETS, "zani_cache_maker.png"),
    "chat": os.path.join(ASSETS, "zani_chat.png"),
    "act": os.path.join(ASSETS, "zani_act.png"),
}


# ==========================================================
# SAFE DISPLAY HELPERS
# ==========================================================

def show(name):
    path = IMAGES.get(name)
    if not path:
        return
    if not os.path.exists(path):
        print(f"[Missing asset: {path}]")
        return
    render_logo(path)


def show_init():
    show("init")


def show_threshold():
    show("threshold")


def show_cache_maker():
    show("cache")


def show_chat():
    show("chat")


def show_act():
    show("act")