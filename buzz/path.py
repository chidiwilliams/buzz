import os
import sys


def resolve_path(path: str):
    """Returns the absolute path to the given file or folder. It handles the path resolution both when the app is run
    directly through Python and when it is bundled via PyInstaller."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), path)
    return os.path.join(os.path.dirname(__file__), '..', path)
