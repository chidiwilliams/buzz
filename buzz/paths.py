import os
import re


WINDOWS_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def file_path_as_title(file_path: str):
    return os.path.basename(file_path)


def safe_filename_component(name: str, fallback: str = "transcript") -> str:
    """Make metadata safe to use as one portable filename component."""
    sanitized = WINDOWS_INVALID_FILENAME_CHARS.sub("_", name)
    sanitized = re.sub(r"[ .]$", "#", sanitized)

    if not sanitized:
        return fallback

    windows_stem = sanitized.split(".", 1)[0].rstrip(" .").upper()
    if windows_stem in WINDOWS_RESERVED_FILENAMES:
        sanitized = f"_{sanitized}"

    return sanitized
