import os
import sys

APP_BASE_DIR = (
    getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    if getattr(sys, "frozen", False)
    else os.path.dirname(__file__)
)


def get_path(path: str):
    return os.path.join(APP_BASE_DIR, path)
