import os
import sys


def get_asset_path(path: str):
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "buzz", path)
    return os.path.join(os.path.dirname(__file__), path)
