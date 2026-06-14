"""
Discovery, download and dynamic loading of Buzz plugins.

Plugins live as folders under ``<user_cache_dir>/Buzz/plugins/<plugin_id>/`` and
are loaded by importing their ``plugin.py`` entry module and locating the single
:class:`BuzzPlugin` subclass it defines. A bundled test plugin shipped in the
``buzz/plugins`` source tree is copied into the user-writable folder on first
launch.
"""

import importlib.util
import inspect
import logging
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List
from urllib.request import urlopen

from platformdirs import user_cache_dir

from buzz.assets import get_path
from buzz.plugins.base import BuzzPlugin

logger = logging.getLogger(__name__)

# Bundled plugins shipped in the source tree and copied to the user folder on
# first launch.
BUNDLED_PLUGIN_IDS = ["ai_summary", "transcript_resizer"]

ENTRY_MODULE = "plugin.py"


class PluginLoadError(Exception):
    """Raised when a plugin folder cannot be loaded into a BuzzPlugin instance."""


def get_plugins_dir() -> str:
    path = os.path.join(user_cache_dir("Buzz"), "plugins")
    os.makedirs(path, exist_ok=True)
    return path


def get_plugins_deps_dir() -> str:
    path = os.path.join(user_cache_dir("Buzz"), "plugins_deps")
    os.makedirs(path, exist_ok=True)
    return path


def ensure_deps_on_path() -> None:
    """Ensure the plugin dependencies folder is importable."""
    deps_dir = get_plugins_deps_dir()
    if deps_dir not in sys.path:
        sys.path.insert(0, deps_dir)


def copy_bundled_plugins() -> None:
    """Copy bundled plugins into the user plugins folder if not already present."""
    plugins_dir = get_plugins_dir()
    for plugin_id in BUNDLED_PLUGIN_IDS:
        dest = os.path.join(plugins_dir, plugin_id)
        if os.path.exists(dest):
            continue
        src = get_path(os.path.join("plugins", plugin_id))
        if not os.path.isdir(src):
            logger.warning("Bundled plugin source not found: %s", src)
            continue
        try:
            shutil.copytree(src, dest)
            logger.info("Copied bundled plugin '%s' to %s", plugin_id, dest)
        except Exception as exc:
            logger.warning("Failed to copy bundled plugin '%s': %s", plugin_id, exc)


def discover_plugin_dirs() -> List[str]:
    """Return paths of plugin folders (subdirs containing the entry module)."""
    plugins_dir = get_plugins_dir()
    dirs = []
    for name in sorted(os.listdir(plugins_dir)):
        path = os.path.join(plugins_dir, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, ENTRY_MODULE)):
            dirs.append(path)
    return dirs


def load_plugin_from_dir(path: str) -> BuzzPlugin:
    """Import a plugin folder and instantiate its BuzzPlugin subclass.

    Raises:
        PluginLoadError: if the folder has no valid plugin entry / subclass.
    """
    entry = os.path.join(path, ENTRY_MODULE)
    if not os.path.isfile(entry):
        raise PluginLoadError(f"No {ENTRY_MODULE} found in {path}")

    module_name = f"buzz_plugin_{os.path.basename(path)}"
    spec = importlib.util.spec_from_file_location(module_name, entry)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"Could not create import spec for {entry}")

    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses / relative references resolve.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise PluginLoadError(f"Error importing {entry}: {exc}") from exc

    plugin_classes = [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, BuzzPlugin)
        and obj is not BuzzPlugin
        and obj.__module__ == module_name
    ]
    if len(plugin_classes) == 0:
        raise PluginLoadError(f"No BuzzPlugin subclass found in {entry}")
    if len(plugin_classes) > 1:
        raise PluginLoadError(
            f"Multiple BuzzPlugin subclasses found in {entry}; expected exactly one"
        )

    plugin_cls = plugin_classes[0]
    metadata = getattr(plugin_cls, "metadata", None)
    if metadata is None or not getattr(metadata, "id", None):
        raise PluginLoadError(
            f"Plugin {plugin_cls.__name__} is missing a metadata.id"
        )

    try:
        return plugin_cls()
    except Exception as exc:
        raise PluginLoadError(f"Error instantiating {plugin_cls.__name__}: {exc}") from exc


def _safe_extract(zip_file: zipfile.ZipFile, dest_dir: str) -> None:
    """Extract a zip, guarding against path traversal (zip-slip)."""
    dest_root = os.path.realpath(dest_dir)
    for member in zip_file.namelist():
        target = os.path.realpath(os.path.join(dest_dir, member))
        if not (target == dest_root or target.startswith(dest_root + os.sep)):
            raise PluginLoadError(f"Unsafe path in archive: {member}")
    zip_file.extractall(dest_dir)


def _find_plugin_root(extracted_dir: str) -> str:
    """Locate the folder containing the entry module within an extracted archive.

    Supports archives that contain the plugin files at the top level or nested in
    a single wrapping directory (the common case for GitHub-style zips).
    """
    if os.path.isfile(os.path.join(extracted_dir, ENTRY_MODULE)):
        return extracted_dir
    entries = [
        os.path.join(extracted_dir, name) for name in os.listdir(extracted_dir)
    ]
    subdirs = [p for p in entries if os.path.isdir(p)]
    if len(subdirs) == 1 and os.path.isfile(os.path.join(subdirs[0], ENTRY_MODULE)):
        return subdirs[0]
    raise PluginLoadError(
        f"Archive does not contain a {ENTRY_MODULE} at its root or in a single folder"
    )


def download_and_extract(url: str) -> str:
    """Download a plugin zip from ``url``, validate it, and install it.

    Returns the installed plugin's id. Raises PluginLoadError on any failure;
    leaves no partial install behind.
    """
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = os.path.join(tmp, "plugin.zip")
        try:
            with urlopen(url, timeout=60) as response:
                with open(archive_path, "wb") as f:
                    shutil.copyfileobj(response, f)
        except Exception as exc:
            raise PluginLoadError(f"Failed to download plugin: {exc}") from exc

        extracted = os.path.join(tmp, "extracted")
        os.makedirs(extracted, exist_ok=True)
        try:
            with zipfile.ZipFile(archive_path) as zf:
                _safe_extract(zf, extracted)
        except zipfile.BadZipFile as exc:
            raise PluginLoadError(f"Downloaded file is not a valid zip: {exc}") from exc

        plugin_root = _find_plugin_root(extracted)

        # Validate by loading before committing to the plugins folder.
        plugin = load_plugin_from_dir(plugin_root)
        plugin_id = plugin.metadata.id

        dest = os.path.join(get_plugins_dir(), plugin_id)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(plugin_root, dest)

    return plugin_id
