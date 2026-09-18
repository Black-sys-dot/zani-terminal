import os
from PIL import Image


# ==========================================================
# ANSI IMAGE RENDERER (YOUR SCRIPT — UNTOUCHED)
# ==========================================================

import subprocess

def render_logo(image_path, width=60):
    try:
        # We use chafa to render the image in the terminal natively
        subprocess.run(["chafa", "--size", str(width), image_path])
    except FileNotFoundError:
        # Fallback if chafa is somehow not installed
        print(f"[Image: {os.path.basename(image_path)}]")


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