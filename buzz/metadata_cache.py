"""Cache of data gathered while transcribing, kept per transcription.

Transcription engines and speaker identification produce more than the
segments Buzz saves, e.g. word probabilities, ``no_speech_prob`` or the
diarization turns. That data is kept as JSON files in
``<user_cache_dir>/Buzz/metadata/<transcription id>/<name>.json`` so plugins and
other parts of the app can use it later. See ``buzz/plugins/AGENTS.md`` for the
files that are written.

The transcription id is the ``transcription.id`` column, i.e.
``FileTranscriptionTask.uid``. The folder is deleted with the transcription.

Writing metadata must never fail a transcription, so the ``save_*`` functions
log errors and return ``None`` instead of raising.
"""

import dataclasses
import json
import logging
import math
import os
import re
import shutil
import tempfile
from typing import Any, List, Optional, Union
from uuid import UUID

from platformdirs import user_cache_dir

METADATA_DIR_ENV = "BUZZ_METADATA_DIR"

WHISPER_CPP = "whisper_cpp"
FASTER_WHISPER = "faster_whisper"
OPENAI_WHISPER = "openai_whisper"
HUGGING_FACE = "hugging_face"
OPENAI_API = "openai_api"
SPEAKER_IDENTIFICATION = "speaker_identification"

# Deeper nesting is turned into text, so cyclic objects can't recurse forever
MAX_DEPTH = 32

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

TranscriptionId = Union[UUID, str]


def metadata_root() -> str:
    """Folder that holds the metadata folders of all transcriptions."""
    return os.environ.get(METADATA_DIR_ENV) or os.path.join(
        user_cache_dir("Buzz"), "metadata"
    )


def metadata_dir(transcription_id: TranscriptionId) -> str:
    """Metadata folder of one transcription. It may not exist yet."""
    # Parsing as a UUID keeps an id from pointing outside the metadata root
    return os.path.join(metadata_root(), str(UUID(str(transcription_id))))


def metadata_path(transcription_id: TranscriptionId, name: str) -> str:
    """Path of the ``name`` metadata file of a transcription."""
    if not _NAME_PATTERN.match(name) or name.endswith(".json"):
        raise ValueError(f"Invalid metadata name: {name!r}")
    return os.path.join(metadata_dir(transcription_id), f"{name}.json")


def to_jsonable(value: Any, _depth: int = 0) -> Any:
    """Convert ``value`` to plain JSON types.

    Handles dataclasses, named tuples, pydantic models, numpy and torch values
    and objects with attributes. Infinite and NaN floats become ``None``, as
    JSON has no such values and strict parsers reject them. Anything else, or
    anything nested too deeply, becomes its ``str()``.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if _depth > MAX_DEPTH:
        return str(value)

    def convert(item):
        return to_jsonable(item, _depth + 1)

    if isinstance(value, dict):
        return {str(key): convert(item) for key, item in value.items()}
    if isinstance(value, tuple) and hasattr(type(value), "_fields"):  # named tuple
        return convert(value._asdict())
    if isinstance(value, (list, tuple, set, frozenset)):
        return [convert(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return convert(
            {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
        )
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    # pydantic models, e.g. OpenAI responses
    dumped = _call_if_callable(value, "model_dump")
    if isinstance(dumped, dict):
        return convert(dumped)
    # numpy arrays and scalars, torch tensors
    listed = _call_if_callable(value, "tolist")
    if isinstance(listed, (list, bool, int, float)):
        return convert(listed)
    attributes = getattr(value, "__dict__", None)
    if isinstance(attributes, dict):
        return convert(
            {key: item for key, item in attributes.items() if not key.startswith("_")}
        )
    return str(value)


def _call_if_callable(value: Any, method_name: str) -> Any:
    method = getattr(value, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _write_atomically(path: str, write) -> None:
    """Write through a temp file, so readers never see a half written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as file:
            write(file)
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def save_metadata(
    transcription_id: Optional[TranscriptionId], name: str, data: Any
) -> Optional[str]:
    """Save ``data`` as the ``name`` metadata of a transcription.

    Replaces an earlier file of the same name. Returns the file path, or
    ``None`` if there is no transcription id or the file could not be written.
    """
    if transcription_id is None:
        return None
    try:
        path = metadata_path(transcription_id, name)
        content = json.dumps(
            to_jsonable(data), ensure_ascii=False, allow_nan=False, indent=1
        ).encode("utf-8")
        _write_atomically(path, lambda file: file.write(content))
        return path
    except Exception:
        logging.exception("Failed to save %s metadata of %s", name, transcription_id)
        return None


def save_metadata_file(
    transcription_id: Optional[TranscriptionId], name: str, source_path: str
) -> Optional[str]:
    """Save a JSON file as it is as the ``name`` metadata of a transcription.

    For tool output that should be kept byte for byte. Returns the file path,
    or ``None`` if there is no transcription id or the file could not be copied.
    """
    if transcription_id is None:
        return None
    try:
        path = metadata_path(transcription_id, name)

        def copy(file):
            with open(source_path, "rb") as source:
                shutil.copyfileobj(source, file)

        _write_atomically(path, copy)
        return path
    except Exception:
        logging.exception("Failed to save %s metadata of %s", name, transcription_id)
        return None


def load_metadata(transcription_id: TranscriptionId, name: str) -> Optional[Any]:
    """The ``name`` metadata of a transcription, or ``None`` if there is none."""
    path = metadata_path(transcription_id, name)
    try:
        with open(path, "rb") as file:
            return json.loads(file.read().decode("utf-8"))
    except FileNotFoundError:
        return None


def list_metadata(transcription_id: TranscriptionId) -> List[str]:
    """Names of the metadata saved for a transcription, sorted."""
    try:
        file_names = os.listdir(metadata_dir(transcription_id))
    except (FileNotFoundError, NotADirectoryError):
        return []
    return sorted(
        file_name[: -len(".json")]
        for file_name in file_names
        if file_name.endswith(".json")
    )


def delete_metadata(transcription_id: TranscriptionId) -> None:
    """Delete all metadata of a transcription."""
    try:
        directory = metadata_dir(transcription_id)
    except ValueError:
        logging.warning("Not deleting metadata of invalid id %r", transcription_id)
        return
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        pass
    except OSError:
        logging.exception("Failed to delete metadata of %s", transcription_id)


def copy_metadata(source_id: TranscriptionId, target_id: TranscriptionId) -> None:
    """Copy the metadata of a transcription to its copy.

    Files the target already has are kept.
    """
    try:
        source_dir = metadata_dir(source_id)
        target_dir = metadata_dir(target_id)
        if not os.path.isdir(source_dir):
            return
        os.makedirs(target_dir, exist_ok=True)
        for file_name in os.listdir(source_dir):
            if not file_name.endswith(".json"):
                continue
            target_path = os.path.join(target_dir, file_name)
            if not os.path.exists(target_path):
                shutil.copyfile(os.path.join(source_dir, file_name), target_path)
    except Exception:
        logging.exception("Failed to copy metadata of %s to %s", source_id, target_id)
