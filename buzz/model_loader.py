import enum
import hashlib
import logging
import os
import time
import threading
import shutil
import subprocess
import sys
import warnings
import platform
import requests
import whisper
import huggingface_hub
import zipfile
from dataclasses import dataclass
from typing import Optional, List

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable
from platformdirs import user_cache_dir
from huggingface_hub.errors import LocalEntryNotFoundError

from buzz.locale import _

# On Windows, creating symlinks requires special privileges (Developer Mode or
# SeCreateSymbolicLinkPrivilege). Monkey-patch huggingface_hub to use file
# copying instead of symlinks to avoid [WinError 1314] errors.
if sys.platform == "win32":
    try:
        from huggingface_hub import file_download
        from pathlib import Path

        _original_create_symlink = file_download._create_symlink

        def _windows_create_symlink(src: Path, dst: Path, new_blob: bool = False) -> None:
            """Windows-compatible replacement that copies instead of symlinking."""
            src = Path(src)
            dst = Path(dst)

            # If dst already exists and is correct, skip
            if dst.exists():
                if dst.is_symlink():
                    # Existing symlink - leave it
                    return
                if dst.is_file():
                    # Check if it's the same file
                    if dst.stat().st_size == src.stat().st_size:
                        return

            dst.parent.mkdir(parents=True, exist_ok=True)

            # Try symlink first (works if Developer Mode is enabled)
            try:
                dst.unlink(missing_ok=True)
                os.symlink(src, dst)
                return
            except OSError:
                pass

            # Fallback: copy the file instead
            dst.unlink(missing_ok=True)
            shutil.copy2(src, dst)

        file_download._create_symlink = _windows_create_symlink
        logging.debug("Patched huggingface_hub to use file copying on Windows")
    except Exception as e:
        logging.warning(f"Failed to patch huggingface_hub for Windows: {e}")


model_root_dir = user_cache_dir("Buzz")
model_root_dir = os.path.join(model_root_dir, "models")
model_root_dir = os.getenv("BUZZ_MODEL_ROOT", model_root_dir)
os.makedirs(model_root_dir, exist_ok=True)

logging.debug("Model root directory: %s", model_root_dir)

class WhisperModelSize(str, enum.Enum):
    TINY = "tiny"
    TINYEN = "tiny.en"
    BASE = "base"
    BASEEN = "base.en"
    SMALL = "small"
    SMALLEN = "small.en"
    MEDIUM = "medium"
    MEDIUMEN = "medium.en"
    LARGE = "large"
    LARGEV2 = "large-v2"
    LARGEV3 = "large-v3"
    LARGEV3TURBO = "large-v3-turbo"
    CUSTOM = "custom"
    LUMII = "lumii"

    def to_faster_whisper_model_size(self) -> str:
        if self == WhisperModelSize.LARGE:
            return "large-v1"
        return self.value

    def to_whisper_cpp_model_size(self) -> str:
        if self == WhisperModelSize.LARGE:
            return "large-v1"
        return self.value

    def __str__(self):
        return self.value.capitalize()

# Approximate expected file sizes for Whisper models (based on actual .pt file sizes)
WHISPER_MODEL_SIZES = {
    WhisperModelSize.TINY: 72 * 1024 * 1024,           # ~73 MB actual
    WhisperModelSize.TINYEN: 72 * 1024 * 1024,         # ~73 MB actual
    WhisperModelSize.BASE: 138 * 1024 * 1024,          # ~139 MB actual
    WhisperModelSize.BASEEN: 138 * 1024 * 1024,        # ~139 MB actual
    WhisperModelSize.SMALL: 460 * 1024 * 1024,         # ~462 MB actual
    WhisperModelSize.SMALLEN: 460 * 1024 * 1024,       # ~462 MB actual
    WhisperModelSize.MEDIUM: 1500 * 1024 * 1024,       # ~1.5 GB actual
    WhisperModelSize.MEDIUMEN: 1500 * 1024 * 1024,     # ~1.5 GB actual
    WhisperModelSize.LARGE: 2870 * 1024 * 1024,        # ~2.9 GB actual
    WhisperModelSize.LARGEV2: 2870 * 1024 * 1024,      # ~2.9 GB actual
    WhisperModelSize.LARGEV3: 2870 * 1024 * 1024,      # ~2.9 GB actual
    WhisperModelSize.LARGEV3TURBO: 1550 * 1024 * 1024, # ~1.6 GB actual (turbo is smaller)
}

def get_expected_whisper_model_size(size: WhisperModelSize) -> Optional[int]:
    """Get expected file size for a Whisper model without network request."""
    return WHISPER_MODEL_SIZES.get(size, None)

class ModelType(enum.Enum):
    WHISPER = "Whisper"
    WHISPER_CPP = "Whisper.cpp"
    HUGGING_FACE = "Hugging Face"
    FASTER_WHISPER = "Faster Whisper"
    OPEN_AI_WHISPER_API = "OpenAI Whisper API"

    @property
    def supports_initial_prompt(self):
        return self in (
            ModelType.WHISPER,
            ModelType.WHISPER_CPP,
            ModelType.OPEN_AI_WHISPER_API,
            ModelType.FASTER_WHISPER,
        )

    def is_available(self):
        if (
            # Hide Faster Whisper option on macOS x86_64
            # See: https://github.com/SYSTRAN/faster-whisper/issues/541
            (self == ModelType.FASTER_WHISPER
                and platform.system() == "Darwin" and platform.machine() == "x86_64")
        ):
            return False
        return True

    def is_manually_downloadable(self):
        return self in (
            ModelType.WHISPER,
            ModelType.WHISPER_CPP,
            ModelType.FASTER_WHISPER,
        )


HUGGING_FACE_MODEL_ALLOW_PATTERNS = [
    "model.safetensors",  # largest by size first
    "pytorch_model.bin",
    "model-00001-of-00002.safetensors",
    "model-00002-of-00002.safetensors",
    "model.safetensors.index.json",
    "added_tokens.json",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "normalizer.json",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
]

# MMS models use different patterns - adapters are downloaded on-demand by transformers
MMS_MODEL_ALLOW_PATTERNS = [
    "model.safetensors",
    "pytorch_model.bin",
    "config.json",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "vocab.json",
    "special_tokens_map.json",
    "added_tokens.json",
]

# ISO 639-1 to ISO 639-3 language code mapping for MMS models
ISO_639_1_TO_3 = {
    "en": "eng", "fr": "fra", "de": "deu", "es": "spa", "it": "ita",
    "pt": "por", "ru": "rus", "ja": "jpn", "ko": "kor", "zh": "cmn",
    "ar": "ara", "hi": "hin", "nl": "nld", "pl": "pol", "sv": "swe",
    "tr": "tur", "uk": "ukr", "vi": "vie", "cs": "ces", "da": "dan",
    "fi": "fin", "el": "ell", "he": "heb", "hu": "hun", "id": "ind",
    "ms": "zsm", "no": "nob", "ro": "ron", "sk": "slk", "th": "tha",
    "bg": "bul", "ca": "cat", "hr": "hrv", "lt": "lit", "lv": "lav",
    "sl": "slv", "et": "est", "sr": "srp", "tl": "tgl", "bn": "ben",
    "ta": "tam", "te": "tel", "mr": "mar", "gu": "guj", "kn": "kan",
    "ml": "mal", "pa": "pan", "ur": "urd", "fa": "pes", "sw": "swh",
    "af": "afr", "az": "azj", "be": "bel", "bs": "bos", "cy": "cym",
    "eo": "epo", "eu": "eus", "ga": "gle", "gl": "glg", "hy": "hye",
    "is": "isl", "ka": "kat", "kk": "kaz", "km": "khm", "lo": "lao",
    "mk": "mkd", "mn": "khk", "my": "mya", "ne": "npi", "si": "sin",
    "sq": "sqi", "uz": "uzn", "zu": "zul", "am": "amh", "jw": "jav",
    "la": "lat", "so": "som", "su": "sun", "tt": "tat", "yo": "yor",
}


def map_language_to_mms(language_code: str) -> str:
    """Convert ISO 639-1 code to ISO 639-3 code for MMS models.

    If the code is already 3 letters, returns it as-is.
    If the code is not found in the mapping, returns as-is.
    """
    if not language_code:
        return "eng"  # Default to English for MMS
    if len(language_code) == 3:
        return language_code  # Already ISO 639-3
    return ISO_639_1_TO_3.get(language_code, language_code)


def is_mms_model(model_id: str) -> bool:
    """Detect if a HuggingFace model is an MMS (Massively Multilingual Speech) model.

    Detection criteria:
    1. Model ID contains "mms-" (e.g., facebook/mms-1b-all)
    2. Model config has model_type == "wav2vec2" with adapter architecture
    """
    if not model_id:
        return False

    # Fast check: model ID pattern
    if "mms-" in model_id.lower():
        return True

    # For cached/downloaded models, check config.json
    try:
        import json
        config_path = huggingface_hub.hf_hub_download(
            model_id, "config.json", local_files_only=True, cache_dir=model_root_dir
        )
        with open(config_path) as f:
            config = json.load(f)
        # MMS models have model_type "wav2vec2" and use adapter architecture
        return (config.get("model_type") == "wav2vec2"
                and config.get("adapter_attn_dim") is not None)
    except Exception:
        return False


@dataclass()
class TranscriptionModel:
    def __init__(
        self,
        model_type: ModelType = ModelType.WHISPER,
        whisper_model_size: Optional[WhisperModelSize] = WhisperModelSize.TINY,
        hugging_face_model_id: Optional[str] = ""
    ):
        self.model_type = model_type
        self.whisper_model_size = whisper_model_size
        self.hugging_face_model_id = hugging_face_model_id

    def __str__(self):
        match self.model_type:
            case ModelType.WHISPER:
                return f"Whisper ({self.whisper_model_size})"
            case ModelType.WHISPER_CPP:
                return f"Whisper.cpp ({self.whisper_model_size})"
            case ModelType.HUGGING_FACE:
                return f"Hugging Face ({self.hugging_face_model_id})"
            case ModelType.FASTER_WHISPER:
                return f"Faster Whisper ({self.whisper_model_size})"
            case ModelType.OPEN_AI_WHISPER_API:
                return "OpenAI Whisper API"
            case _:
                raise Exception("Unknown model type")

    def is_deletable(self):
        return (
            self.model_type == ModelType.WHISPER
            or self.model_type == ModelType.WHISPER_CPP
            or self.model_type == ModelType.FASTER_WHISPER
        ) and self.get_local_model_path() is not None

    def open_file_location(self):
        model_path = self.get_local_model_path()

        if (self.model_type == ModelType.HUGGING_FACE
                or self.model_type == ModelType.FASTER_WHISPER):
            model_path = os.path.dirname(model_path)

        if model_path is None:
            return
        self.open_path(path=os.path.dirname(model_path))

    @staticmethod
    def default():
        model_type = next(
            model_type for model_type in ModelType if model_type.is_available()
        )
        return TranscriptionModel(model_type=model_type)

    @staticmethod
    def open_path(path: str):
        if sys.platform == "win32":
            os.startfile(path)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, path])

    def delete_local_file(self):
        model_path = self.get_local_model_path()

        if self.model_type in (ModelType.HUGGING_FACE,
                               ModelType.FASTER_WHISPER):
            # Go up two directories to get the huggingface cache root for this model
            # Structure: models--repo--name/snapshots/xxx/files
            model_path = os.path.dirname(os.path.dirname(model_path))

            logging.debug("Deleting model directory: %s", model_path)

            shutil.rmtree(model_path, ignore_errors=True)
            return

        if self.model_type == ModelType.WHISPER_CPP:
            if self.whisper_model_size == WhisperModelSize.CUSTOM:
                # Custom models are stored as a single .bin file directly in model_root_dir
                logging.debug("Deleting model file: %s", model_path)
                os.remove(model_path)
            else:
                # Non-custom models are downloaded via huggingface_hub.
                # Multiple models share the same repo directory, so we only delete
                # the specific model files, not the entire directory.
                logging.debug("Deleting model file: %s", model_path)
                os.remove(model_path)

                # Also delete CoreML files if they exist (.mlmodelc.zip and extracted directory)
                model_dir = os.path.dirname(model_path)
                model_name = self.whisper_model_size.to_whisper_cpp_model_size()
                coreml_zip = os.path.join(model_dir, f"ggml-{model_name}-encoder.mlmodelc.zip")
                coreml_dir = os.path.join(model_dir, f"ggml-{model_name}-encoder.mlmodelc")

                if os.path.exists(coreml_zip):
                    logging.debug("Deleting CoreML zip: %s", coreml_zip)
                    os.remove(coreml_zip)
                if os.path.exists(coreml_dir):
                    logging.debug("Deleting CoreML directory: %s", coreml_dir)
                    shutil.rmtree(coreml_dir, ignore_errors=True)
            return

        logging.debug("Deleting model file: %s", model_path)
        os.remove(model_path)

    def get_local_model_path(self) -> Optional[str]:
        if self.model_type == ModelType.WHISPER_CPP:
            file_path = get_whisper_cpp_file_path(size=self.whisper_model_size)
            if not file_path or not os.path.exists(file_path) or not os.path.isfile(file_path):
                return None
            return file_path

        if self.model_type == ModelType.WHISPER:
            file_path = get_whisper_file_path(size=self.whisper_model_size)
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                return None
            
            file_size = os.path.getsize(file_path)

            expected_size = get_expected_whisper_model_size(self.whisper_model_size)

            if expected_size is not None:
                if file_size < expected_size * 0.95: # Allow 5% tolerance for file system differences
                    return None
                return file_path
            else: 
                # For unknown model size            
                if file_size < 50 * 1024 * 1024:
                    return None
                
                return file_path                

        if self.model_type == ModelType.FASTER_WHISPER:
            try:
                return download_faster_whisper_model(
                    model=self, local_files_only=True
                )
            except (ValueError, FileNotFoundError):
                return None

        if self.model_type == ModelType.OPEN_AI_WHISPER_API:
            return ""

        if self.model_type == ModelType.HUGGING_FACE:
            try:
                return huggingface_hub.snapshot_download(
                    self.hugging_face_model_id,
                    allow_patterns=HUGGING_FACE_MODEL_ALLOW_PATTERNS,
                    local_files_only=True,
                    cache_dir=model_root_dir,
                    etag_timeout=60
                )
            except (ValueError, FileNotFoundError):
                return None

        raise Exception("Unknown model type")


WHISPER_CPP_REPO_ID = "ggerganov/whisper.cpp"
WHISPER_CPP_LUMII_REPO_ID = "RaivisDejus/whisper.cpp-lv"


def get_whisper_cpp_file_path(size: WhisperModelSize) -> str:
    if size == WhisperModelSize.CUSTOM:
        return os.path.join(model_root_dir, f"ggml-model-whisper-custom.bin")

    repo_id = WHISPER_CPP_REPO_ID

    if size == WhisperModelSize.LUMII:
        repo_id = WHISPER_CPP_LUMII_REPO_ID

    model_filename = f"ggml-{size.to_whisper_cpp_model_size()}.bin"

    try:
        model_path = huggingface_hub.snapshot_download(
            repo_id=repo_id,
            allow_patterns=[model_filename],
            local_files_only=True,
            cache_dir=model_root_dir,
            etag_timeout=60
        )

        return os.path.join(model_path, model_filename)
    except LocalEntryNotFoundError:
        return ''


def get_whisper_file_path(size: WhisperModelSize) -> str:
    root_dir = os.path.join(model_root_dir, "whisper")

    if size == WhisperModelSize.CUSTOM:
        return os.path.join(root_dir, "custom")

    url = whisper._MODELS[size.value]
    return os.path.join(root_dir, os.path.basename(url))


class HuggingfaceDownloadMonitor:
    def __init__(self, model_root: str, progress: pyqtSignal(tuple), total_file_size: int):
        self.model_root = model_root
        self.progress = progress
        # To keep dialog open even if it reports 100%
        self.total_file_size = round(total_file_size * 1.1)
        self.incomplete_download_root = None
        self.stop_event = threading.Event()
        self.monitor_thread = None
        self.set_download_roots()

    def set_download_roots(self):
        normalized_model_root = os.path.normpath(self.model_root)
        two_dirs_up = os.path.normpath(
            os.path.join(normalized_model_root, "..", ".."))
        self.incomplete_download_root = os.path.normpath(
            os.path.join(two_dirs_up, "blobs"))

    def clean_tmp_files(self):
        for filename in os.listdir(model_root_dir):
            if filename.startswith("tmp"):
                os.remove(os.path.join(model_root_dir, filename))

    def monitor_file_size(self):
        while not self.stop_event.is_set():
            try:
                if model_root_dir is not None and os.path.isdir(model_root_dir):
                    for filename in os.listdir(model_root_dir):
                        if filename.startswith("tmp"):
                            try:
                                file_size = os.path.getsize(
                                    os.path.join(model_root_dir, filename))
                                self.progress.emit((file_size, self.total_file_size))
                            except OSError:
                                pass  # File may have been deleted

                if self.incomplete_download_root and os.path.isdir(self.incomplete_download_root):
                    for filename in os.listdir(self.incomplete_download_root):
                        if filename.endswith(".incomplete"):
                            try:
                                file_size = os.path.getsize(os.path.join(
                                    self.incomplete_download_root, filename))
                                self.progress.emit((file_size, self.total_file_size))
                            except OSError:
                                pass  # File may have been deleted
            except OSError:
                pass  # Directory listing failed, ignore

            time.sleep(2)

    def start_monitoring(self):
        self.clean_tmp_files()
        self.monitor_thread = threading.Thread(target=self.monitor_file_size)
        self.monitor_thread.start()

    def stop_monitoring(self):
        self.progress.emit((self.total_file_size, self.total_file_size))

        if self.monitor_thread is not None:
            self.stop_event.set()
            self.monitor_thread.join()


def get_file_size(url):
    response = requests.head(url, allow_redirects=True)
    response.raise_for_status()
    return int(response.headers['Content-Length'])


def download_from_huggingface(
        repo_id: str,
        allow_patterns: List[str],
        progress: pyqtSignal(tuple),
        num_large_files: int = 1
):
    progress.emit((0, 100))

    try:
        model_root = huggingface_hub.snapshot_download(
            repo_id,
            # all, but largest
            allow_patterns=allow_patterns[num_large_files:],
            cache_dir=model_root_dir,
            etag_timeout=60
        )
    except Exception as exc:
        logging.exception(exc)
        return ""

    progress.emit((1, 100))

    largest_file_size = 0
    for pattern in allow_patterns[:num_large_files]:
        try:
            file_url = huggingface_hub.hf_hub_url(repo_id, pattern)
            file_size = get_file_size(file_url)

            if file_size > largest_file_size:
                largest_file_size = file_size

        except requests.exceptions.RequestException as e:
            continue

    model_download_monitor = HuggingfaceDownloadMonitor(
        model_root, progress, largest_file_size)
    model_download_monitor.start_monitoring()

    try:
        huggingface_hub.snapshot_download(
            repo_id,
            allow_patterns=allow_patterns[:num_large_files],  # largest
            cache_dir=model_root_dir,
            etag_timeout=60
        )
    except Exception as exc:
        logging.exception(exc)
        model_download_monitor.stop_monitoring()

        return ""

    model_download_monitor.stop_monitoring()

    return model_root


def download_faster_whisper_model(
    model: TranscriptionModel, local_files_only=False, progress: pyqtSignal(tuple) = None
):
    size = model.whisper_model_size.to_faster_whisper_model_size()
    custom_repo_id = model.hugging_face_model_id

    if size == WhisperModelSize.CUSTOM and custom_repo_id == "":
        raise ValueError("Custom model id is not provided")

    if size == WhisperModelSize.CUSTOM:
        repo_id = custom_repo_id
    # Replicating models from faster-whisper code https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py#L29
    elif size == WhisperModelSize.LARGEV3TURBO:
        repo_id = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    else:
        repo_id = "Systran/faster-whisper-%s" % size

    allow_patterns = [
        "model.bin",  # largest by size first
        "pytorch_model.bin",  # possible alternative model filename
        "config.json",
        "preprocessor_config.json",
        "tokenizer.json",
        "vocabulary.*",
    ]

    if local_files_only:
        return huggingface_hub.snapshot_download(
            repo_id,
            allow_patterns=allow_patterns,
            local_files_only=True,
            cache_dir=model_root_dir,
            etag_timeout=60
        )

    return download_from_huggingface(
        repo_id,
        allow_patterns=allow_patterns,
        progress=progress,
        num_large_files=2
    )


class ModelDownloader(QRunnable):
    class Signals(QObject):
        finished = pyqtSignal(str)
        progress = pyqtSignal(tuple)  # (current, total)
        error = pyqtSignal(str)

    def __init__(self, model: TranscriptionModel, custom_model_url: Optional[str] = None):
        super().__init__()

        self.is_coreml_supported = platform.system(
        ) == "Darwin" and platform.machine() == "arm64"
        self.signals = self.Signals()
        self.model = model
        self.stopped = False
        self.custom_model_url = custom_model_url

    def run(self) -> None:
        logging.debug("Downloading model: %s, %s", self.model,
                      self.model.hugging_face_model_id)

        if self.model.model_type == ModelType.WHISPER_CPP:
            if self.custom_model_url:
                url = self.custom_model_url
                file_path = get_whisper_cpp_file_path(
                    size=self.model.whisper_model_size)
                return self.download_model_to_path(url=url, file_path=file_path)

            repo_id = WHISPER_CPP_REPO_ID

            if self.model.whisper_model_size == WhisperModelSize.LUMII:
                repo_id = WHISPER_CPP_LUMII_REPO_ID

            model_name = self.model.whisper_model_size.to_whisper_cpp_model_size()

            whisper_cpp_model_files = [
                f"ggml-{model_name}.bin",
                "README.md"
            ]
            num_large_files = 1
            if self.is_coreml_supported:
                whisper_cpp_model_files = [
                    f"ggml-{model_name}.bin",
                    f"ggml-{model_name}-encoder.mlmodelc.zip",
                    "README.md"
                ]
                num_large_files = 2

            model_path = download_from_huggingface(
                repo_id=repo_id,
                allow_patterns=whisper_cpp_model_files,
                progress=self.signals.progress,
                num_large_files=num_large_files
            )

            if self.is_coreml_supported:
                import tempfile

                target_dir = os.path.join(model_path, f"ggml-{model_name}-encoder.mlmodelc")
                zip_path = os.path.join(model_path, f"ggml-{model_name}-encoder.mlmodelc.zip")

                # Remove target directory if it exists
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)

                # Extract to a temporary directory first
                with tempfile.TemporaryDirectory() as temp_dir:
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_dir)

                    # Remove __MACOSX metadata folders if present
                    macosx_path = os.path.join(temp_dir, "__MACOSX")
                    if os.path.exists(macosx_path):
                        shutil.rmtree(macosx_path)

                    # Check if there's a single top-level directory
                    temp_contents = os.listdir(temp_dir)
                    if len(temp_contents) == 1 and os.path.isdir(os.path.join(temp_dir, temp_contents[0])):
                        # Single directory - move its contents to target
                        nested_dir = os.path.join(temp_dir, temp_contents[0])
                        shutil.move(nested_dir, target_dir)
                    else:
                        # Multiple items or files - copy everything to target
                        os.makedirs(target_dir, exist_ok=True)
                        for item in temp_contents:
                            src = os.path.join(temp_dir, item)
                            dst = os.path.join(target_dir, item)
                            if os.path.isdir(src):
                                shutil.copytree(src, dst)
                            else:
                                shutil.copy2(src, dst)

            self.signals.finished.emit(os.path.join(
                model_path, f"ggml-{model_name}.bin"))
            return

        if self.model.model_type == ModelType.WHISPER:
            url = whisper._MODELS[self.model.whisper_model_size.value]
            file_path = get_whisper_file_path(
                size=self.model.whisper_model_size)
            expected_sha256 = url.split("/")[-2]
            return self.download_model_to_path(
                url=url, file_path=file_path, expected_sha256=expected_sha256
            )

        if self.model.model_type == ModelType.FASTER_WHISPER:
            model_path = download_faster_whisper_model(
                model=self.model,
                progress=self.signals.progress,
            )

            if model_path == "":
                self.signals.error.emit(_("Error"))

            self.signals.finished.emit(model_path)
            return

        if self.model.model_type == ModelType.HUGGING_FACE:
            model_path = download_from_huggingface(
                self.model.hugging_face_model_id,
                allow_patterns=HUGGING_FACE_MODEL_ALLOW_PATTERNS,
                progress=self.signals.progress,
                num_large_files=4
            )

            if model_path == "":
                self.signals.error.emit(_("Error"))

            self.signals.finished.emit(model_path)
            return

        if self.model.model_type == ModelType.OPEN_AI_WHISPER_API:
            self.signals.finished.emit("")
            return

        raise Exception("Invalid model type: " + self.model.model_type.value)

    def download_model_to_path(
        self, url: str, file_path: str, expected_sha256: Optional[str] = None
    ):
        try:
            downloaded = self.download_model(url, file_path, expected_sha256)
            if downloaded:
                self.signals.finished.emit(file_path)
        except requests.RequestException as e:
            self.signals.error.emit(_("A connection error occurred"))
            if not self.stopped and "timeout" not in str(e).lower():
                if os.path.exists(file_path):
                    os.remove(file_path)
            logging.exception("")
        except Exception as exc:
            self.signals.error.emit(str(exc))
            if not self.stopped:
                if os.path.exists(file_path):
                    os.remove(file_path)
                logging.exception(exc)

    def download_model(
        self, url: str, file_path: str, expected_sha256: Optional[str]
    ) -> bool:
        logging.debug(f"Downloading model from {url} to {file_path}")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        if os.path.exists(file_path) and not os.path.isfile(file_path):
            raise RuntimeError(f"{file_path} exists and is not a regular file")

        resume_from = 0
        file_mode = "wb"

        if os.path.isfile(file_path):
            file_size = os.path.getsize(file_path)

            if expected_sha256 is not None:
                # Get the expected file size from URL
                try:
                    head_response = requests.head(url, timeout=5, allow_redirects=True)
                    expected_size = int(head_response.headers.get("Content-Length", 0))

                    if expected_size > 0:
                        if file_size < expected_size:
                            resume_from = file_size
                            file_mode = "ab"
                            logging.debug(
                                f"File incomplete ({file_size}/{expected_size} bytes), resuming from byte {resume_from}"
                            )
                        elif file_size == expected_size:
                            # This means file size matches - verify SHA256 to confirm it is complete
                            try:
                                # Use chunked reading to avoid loading entire file into memory
                                sha256_hash = hashlib.sha256()
                                with open(file_path, "rb") as f:
                                    for chunk in iter(lambda: f.read(8192), b""):
                                        sha256_hash.update(chunk)
                                model_sha256 = sha256_hash.hexdigest()
                                if model_sha256 == expected_sha256:
                                    logging.debug("Model already downloaded and verified")
                                    return True
                                else:
                                    warnings.warn(
                                        f"{file_path} exists, but the SHA256 checksum does not match; re-downloading the file"
                                    )
                                    # File exists but it is wrong, delete it
                                    os.remove(file_path)
                            except Exception as e:
                                logging.warning(f"Error checking existing file: {e}")
                                os.remove(file_path)
                        else:
                            # File is larger than expected - corrupted, delete it
                            warnings.warn(f"File size ({file_size}) exceeds expected size ({expected_size}), re-downloading")
                            os.remove(file_path)                        
                    else:
                        # Can't get expected size - use threshold approach
                        if file_size < 10 * 1024 * 1024:
                            resume_from = file_size
                            file_mode = "ab"  # Append mode to resume
                            logging.debug(f"Resuming download from byte {resume_from}")
                        else:
                            # Large file - verify SHA256 using chunked reading
                            try:
                                sha256_hash = hashlib.sha256()
                                with open(file_path, "rb") as f:
                                    for chunk in iter(lambda: f.read(8192), b""):
                                        sha256_hash.update(chunk)
                                model_sha256 = sha256_hash.hexdigest()
                                if model_sha256 == expected_sha256:
                                    logging.debug("Model already downloaded and verified")
                                    return True
                                else:
                                    warnings.warn("SHA256 mismatch, re-downloading")
                                    os.remove(file_path)
                            except Exception as e:
                                logging.warning(f"Error verifying file: {e}")
                                os.remove(file_path)

                except Exception as e:
                    # Can't get expected size - use threshold
                    logging.debug(f"Could not get expected file size: {e}, using threshold")
                    if file_size < 10 * 1024 * 1024:
                        resume_from = file_size
                        file_mode = "ab"
                        logging.debug(f"Resuming from byte {resume_from}")
            else:
                # No SHA256 to verify - just check file size
                if file_size > 0:
                    resume_from = file_size
                    file_mode = "ab"
                    logging.debug(f"Resuming download from byte {resume_from}")

        # Downloads the model using the requests module instead of urllib to
        # use the certs from certifi when the app is running in frozen mode

        # Check if server supports Range requests before starting download
        supports_range = False
        if resume_from > 0:
            try:
                head_resp = requests.head(url, timeout=10, allow_redirects=True)
                accept_ranges = head_resp.headers.get("Accept-Ranges", "").lower()
                supports_range = accept_ranges == "bytes"
                if not supports_range:
                    logging.debug("Server doesn't support Range requests, starting from beginning")
                    resume_from = 0
                    file_mode = "wb"
            except requests.RequestException as e:
                logging.debug(f"HEAD request failed, starting fresh: {e}")
                resume_from = 0
                file_mode = "wb"

        headers = {}
        if resume_from > 0 and supports_range:
            headers["Range"] = f"bytes={resume_from}-"

        # Use a temporary file for fresh downloads to ensure atomic writes
        temp_file_path = None
        if resume_from == 0:
            temp_file_path = file_path + ".downloading"
            # Clean up any existing temp file
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass
            download_path = temp_file_path
        else:
            download_path = file_path

        try:
            with requests.get(url, stream=True, timeout=30, headers=headers) as source:
                source.raise_for_status()

                if resume_from > 0:
                    if source.status_code == 206:
                        logging.debug(
                            f"Server supports resume, continuing from byte {resume_from}")
                        content_range = source.headers.get("Content-Range", "")
                        if "/" in content_range:
                            total_size = int(content_range.split("/")[-1])
                        else:
                            total_size = resume_from + int(source.headers.get("Content-Length", 0))
                        current = resume_from
                    else:
                        # Server returned 200 instead of 206, need to start over
                        logging.debug("Server returned 200 instead of 206, starting fresh")
                        resume_from = 0
                        file_mode = "wb"
                        temp_file_path = file_path + ".downloading"
                        download_path = temp_file_path
                        total_size = float(source.headers.get("Content-Length", 0))
                        current = 0.0
                else:
                    total_size = float(source.headers.get("Content-Length", 0))
                    current = 0.0

                self.signals.progress.emit((current, total_size))

                with open(download_path, file_mode) as output:
                    for chunk in source.iter_content(chunk_size=8192):
                        if self.stopped:
                            return False
                        output.write(chunk)
                        current += len(chunk)
                        self.signals.progress.emit((current, total_size))

            # If we used a temp file, rename it to the final path
            if temp_file_path and os.path.exists(temp_file_path):
                # Remove existing file if present
                if os.path.exists(file_path):
                    os.remove(file_path)
                shutil.move(temp_file_path, file_path)

        except Exception:
            # Clean up temp file on error
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError:
                    pass
            raise

        if expected_sha256 is not None:
            # Use chunked reading to avoid loading entire file into memory
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(chunk)
            if sha256_hash.hexdigest() != expected_sha256:
                # Delete the corrupted file before raising the error
                try:
                    os.remove(file_path)
                except OSError as e:
                    logging.warning(f"Failed to delete corrupted model file: {e}")
                raise RuntimeError(
                    "Model has been downloaded but the SHA256 checksum does not match. Please retry loading the "
                    "model."
                )

        logging.debug("Downloaded model")

        return True

    def cancel(self):
        self.stopped = True
