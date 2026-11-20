import os
import re
import sys


WINDOWS_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


DOCUMENT_PORTAL_HOST_PATH_XATTR = "user.document-portal.host-path"


def resolve_document_portal_path(path: str) -> str:
    """Map an xdg-desktop-portal document path to the real host path.

    When file dialogs go through the desktop portal (Snap, Flatpak, or apps
    started from a snap such as uv), selected files are exposed as
    /run/user/<uid>/doc/<id>/<name>. Using that path for outputs would write
    them into the portal's private store instead of next to the real file.
    The portal keeps the host path in an extended attribute; use it when this
    process can actually reach that location, otherwise keep the portal path.
    """
    if not path or not sys.platform.startswith("linux"):
        return path
    if not path.startswith(f"/run/user/{os.getuid()}/doc/"):
        return path

    # The file itself (open dialogs) or its document folder (save dialogs,
    # where the file may not exist yet).
    candidates = [(path, ""), (os.path.dirname(path), os.path.basename(path))]
    for candidate, name in candidates:
        try:
            host_path = os.fsdecode(
                os.getxattr(candidate, DOCUMENT_PORTAL_HOST_PATH_XATTR)
            ).rstrip("\x00")
        except (OSError, AttributeError):
            continue
        if not host_path:
            continue
        if name:
            host_path = os.path.join(host_path, name)

        if os.path.exists(host_path):
            mode = os.R_OK | (os.W_OK if os.path.isdir(host_path) else 0)
            if os.access(host_path, mode):
                return host_path
        elif os.access(os.path.dirname(host_path), os.W_OK):
            return host_path
        return path

    return path


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
