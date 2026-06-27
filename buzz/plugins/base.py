"""
Plugin contract for Buzz.

A plugin is a folder containing a ``plugin.py`` module that defines exactly one
subclass of :class:`BuzzPlugin`. The subclass declares its identity, configuration
schema and (optionally) pip dependencies via a ``metadata`` class attribute, and
overrides the lifecycle hooks it cares about.

Thread-safety contract (enforced by the host, important for plugin authors):

- ``before_transcription`` runs on the transcription **worker thread**. It may
  read/modify the source audio file and return a new file path. It must NOT
  touch the database, Qt widgets or anything main-thread bound.
- ``after_transcription`` and ``on_complete`` run on a **background thread** but
  are given access to :class:`PluginContext` whose ``transcription_service`` is
  used by the host on the main thread. Plugins may call it; the host marshals
  the segment save back to the main thread. Plugins must never touch Qt widgets.
"""

import enum
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from buzz.transcriber.transcriber import FileTranscriptionTask, Segment

logger = logging.getLogger(__name__)


def _current_locale() -> str:
    """Return the active UI locale name, e.g. ``lv_LV`` or ``en_US``."""
    try:
        from PyQt6.QtCore import QLocale
        from buzz.settings.settings import Settings

        return Settings().value(Settings.Key.UI_LOCALE, QLocale().name())
    except Exception:  # pragma: no cover - defensive, e.g. no QApplication
        return "en_US"


def plugin_gettext(plugin_file: str) -> Callable[[str], str]:
    """Return a translator function for a plugin, à la Buzz's ``_``.

    Looks for translation files next to the plugin in a ``locale`` folder:
    ``locale/<locale>.json`` (e.g. ``lv_LV.json``) with a fallback to the
    language-only file (``lv.json``). Each file maps the source English string
    to its translation::

        { "AI Summary": "MI kopsavilkums" }

    Usage inside a plugin's ``plugin.py``::

        from buzz.plugins.base import plugin_gettext
        _ = plugin_gettext(__file__)
        ...
        name=_("AI Summary")

    Strings without a translation (or when no locale file exists) fall through
    unchanged, so plugins remain fully usable without any locale files.
    """
    locale_dir = os.path.join(os.path.dirname(os.path.abspath(plugin_file)), "locale")
    locale = _current_locale()
    candidates = [locale]
    if "_" in locale:
        candidates.append(locale.split("_", 1)[0])

    translations: dict = {}
    for name in candidates:
        path = os.path.join(locale_dir, f"{name}.json")
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    translations = json.load(f)
                break
            except (json.JSONDecodeError, IOError) as exc:
                logger.warning("Failed to load plugin locale %s: %s", path, exc)

    def translate(text: str) -> str:
        value = translations.get(text)
        return value if value else text

    return translate


class ConfigFieldType(enum.Enum):
    """The kind of input control a config field maps to in the settings UI."""

    TEXT = "text"  # single line input
    TEXTAREA = "textarea"  # multi-line input
    BOOL = "bool"  # checkbox
    PASSWORD = "password"  # masked input with show toggle, stored in the keyring


@dataclass
class ConfigField:
    """A single configurable parameter exposed by a plugin."""

    key: str
    label: str
    type: ConfigFieldType = ConfigFieldType.TEXT
    default: Any = ""
    description: str = ""
    placeholder: str = ""


@dataclass
class PluginMetadata:
    """Static description of a plugin."""

    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    pip_dependencies: List[str] = field(default_factory=list)
    config_fields: List[ConfigField] = field(default_factory=list)


class PluginContext:
    """Controlled access to Buzz internals handed to each hook invocation."""

    def __init__(self, config: dict, transcription_service, settings, logger):
        # Resolved config values for this plugin, including secrets. Keyed by
        # ConfigField.key.
        self.config = config
        self.transcription_service = transcription_service
        self.settings = settings
        self.log = logger


class BuzzPlugin:
    """Base class for all plugins.

    Subclasses MUST set the ``metadata`` class attribute. All hooks are optional;
    the defaults are no-ops that leave the pipeline unchanged.
    """

    metadata: PluginMetadata

    def before_transcription(
        self, task: "FileTranscriptionTask", context: PluginContext
    ) -> Optional[str]:
        """Run before transcription, after any speech extraction.

        May process the source audio. Return a new file path to use for
        transcription, or ``None`` to leave ``task.file_path`` unchanged.
        Runs on the worker thread — do not touch the database or Qt.
        """
        return None

    def after_transcription(
        self,
        task: "FileTranscriptionTask",
        segments: List["Segment"],
        context: PluginContext,
    ) -> List["Segment"]:
        """Modify or replace the result segments before they are saved.

        Must return a list of segments (return the input unchanged to do nothing).
        Runs on a background thread.
        """
        return segments

    def check_skip(
        self, task: "FileTranscriptionTask", context: PluginContext
    ) -> Optional[List["Segment"]]:
        """Return a list of segments to skip transcription (may be empty), or None to proceed.

        Runs on the worker thread. DB access via context.transcription_service is
        marshaled to the main thread by the host.
        """
        return None

    def on_complete(
        self,
        transcription_id,
        task: "FileTranscriptionTask",
        segments: List["Segment"],
        context: PluginContext,
    ) -> None:
        """Run after the transcription has been saved to the database.

        Use this for side effects keyed on the persisted transcription, e.g.
        writing notes or exporting a file. Runs on a background thread.
        """
        return None
