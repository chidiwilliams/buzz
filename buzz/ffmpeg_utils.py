import os
import shutil
import sys

from buzz.assets import APP_BASE_DIR


def _find_binary(name: str) -> str:
    """Locate an ffmpeg binary, preferring one bundled with a frozen build."""
    path = shutil.which(name)
    if path:
        return path

    search_dirs = [
        getattr(sys, "_MEIPASS", ""),
        APP_BASE_DIR,
        os.path.join(APP_BASE_DIR, "_internal"),
    ]
    for directory in search_dirs:
        if not directory:
            continue
        for candidate in (name, name + ".exe"):
            bundled = os.path.join(directory, candidate)
            if os.path.exists(bundled):
                return bundled

    return name


def find_ffmpeg() -> str:
    return _find_binary("ffmpeg")


def find_ffprobe() -> str:
    return _find_binary("ffprobe")
