"""Registry for user-defined Whisper.cpp custom models.

Older Buzz versions supported a single custom Whisper.cpp model stored at a fixed
path (``ggml-model-whisper-custom.bin``). This module lets users register any
number of custom Whisper.cpp models, each with its own name and model file, while
keeping full backward compatibility with the legacy single-model layout.

The registry is persisted as a JSON list in the existing Buzz ``QSettings`` store,
so no new configuration file or storage mechanism is introduced.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, asdict
from typing import List, Optional

from PyQt6.QtCore import QSettings

APP_NAME = "Buzz"

# QSettings key holding the JSON-encoded list of custom Whisper.cpp models.
_SETTINGS_KEY = "transcriber/whisper-cpp-custom-models"

# The single custom model supported by older Buzz versions was stored at this
# fixed filename inside the model root. Keeping a stable id lets us surface it in
# the new list without moving or re-downloading it.
LEGACY_CUSTOM_MODEL_ID = "legacy-custom"
LEGACY_CUSTOM_MODEL_FILENAME = "ggml-model-whisper-custom.bin"


@dataclass
class CustomWhisperCppModel:
    id: str
    name: str
    path: str
    source_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "CustomWhisperCppModel":
        return CustomWhisperCppModel(
            id=str(data.get("id") or uuid.uuid4()),
            name=data.get("name", ""),
            path=data.get("path", ""),
            source_url=data.get("source_url", ""),
        )


def _settings() -> QSettings:
    return QSettings(APP_NAME, "")


def _load_stored() -> List[CustomWhisperCppModel]:
    raw = _settings().value(_SETTINGS_KEY, "")
    if not raw:
        return []
    try:
        entries = json.loads(raw)
    except (ValueError, TypeError):
        logging.warning("Could not parse custom Whisper.cpp models registry; ignoring it")
        return []
    models: List[CustomWhisperCppModel] = []
    for entry in entries:
        try:
            models.append(CustomWhisperCppModel.from_dict(entry))
        except Exception:
            logging.warning("Skipping invalid custom Whisper.cpp model entry: %r", entry)
    return models


def _save_stored(models: List[CustomWhisperCppModel]) -> None:
    settings = _settings()
    settings.setValue(_SETTINGS_KEY, json.dumps([m.to_dict() for m in models]))
    settings.sync()


def _legacy_model(model_root_dir: str) -> Optional[CustomWhisperCppModel]:
    """Return the pre-existing single custom model as a registry entry, if present."""
    legacy_path = os.path.join(model_root_dir, LEGACY_CUSTOM_MODEL_FILENAME)
    if os.path.isfile(legacy_path):
        return CustomWhisperCppModel(
            id=LEGACY_CUSTOM_MODEL_ID,
            name="Custom Whisper.cpp Model",
            path=legacy_path,
        )
    return None


def get_custom_models(model_root_dir: str) -> List[CustomWhisperCppModel]:
    """All registered custom Whisper.cpp models, including the legacy single model.

    The legacy ``ggml-model-whisper-custom.bin`` file used by older Buzz versions
    is surfaced automatically (without being copied or moved) so that upgrading
    users keep their existing custom model. If a user has explicitly registered an
    entry with the legacy id, that entry takes precedence.
    """
    models = _load_stored()
    if not any(m.id == LEGACY_CUSTOM_MODEL_ID for m in models):
        legacy = _legacy_model(model_root_dir)
        if legacy is not None:
            models = [legacy, *models]
    return models


def get_custom_model(
    model_root_dir: str, model_id: str
) -> Optional[CustomWhisperCppModel]:
    if not model_id:
        return None
    for model in get_custom_models(model_root_dir):
        if model.id == model_id:
            return model
    return None


def add_custom_model(
    name: str,
    path: str,
    source_url: str = "",
    model_id: Optional[str] = None,
) -> CustomWhisperCppModel:
    """Register a custom model and return it.

    ``path`` is stored as-is, so a model file that already exists on the user's
    computer is referenced in place rather than copied.
    """
    models = _load_stored()
    model = CustomWhisperCppModel(
        id=model_id or str(uuid.uuid4()),
        name=name,
        path=path,
        source_url=source_url,
    )
    # Replace an existing entry with the same id instead of duplicating it.
    models = [m for m in models if m.id != model.id]
    models.append(model)
    _save_stored(models)
    return model


def remove_custom_model(model_id: str) -> None:
    """Remove a model from the registry. Does not delete any file on disk."""
    models = [m for m in _load_stored() if m.id != model_id]
    _save_stored(models)


def is_registered_model_file(model_root_dir: str, path: str) -> bool:
    """Whether ``path`` is already registered by one of the custom models."""
    if not path:
        return False
    normalized = os.path.normcase(os.path.abspath(path))
    for model in get_custom_models(model_root_dir):
        if model.path and os.path.normcase(os.path.abspath(model.path)) == normalized:
            return True
    return False
