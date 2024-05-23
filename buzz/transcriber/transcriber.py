import datetime
import enum
import os
import uuid
from dataclasses import dataclass, field
from random import randint
from typing import List, Optional, Tuple, Set

from dataclasses_json import dataclass_json, config, Exclude

from buzz.locale import _
from buzz.model_loader import TranscriptionModel
from buzz.settings.settings import Settings

DEFAULT_WHISPER_TEMPERATURE = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


class Task(enum.Enum):
    TRANSLATE = "translate"
    TRANSCRIBE = "transcribe"


@dataclass
class Segment:
    start: int  # start time in ms
    end: int  # end time in ms
    text: str


LANGUAGES = {
    "en": "english",
    "zh": "chinese",
    "de": "german",
    "es": "spanish",
    "ru": "russian",
    "ko": "korean",
    "fr": "french",
    "ja": "japanese",
    "pt": "portuguese",
    "tr": "turkish",
    "pl": "polish",
    "ca": "catalan",
    "nl": "dutch",
    "ar": "arabic",
    "sv": "swedish",
    "it": "italian",
    "id": "indonesian",
    "hi": "hindi",
    "fi": "finnish",
    "vi": "vietnamese",
    "he": "hebrew",
    "uk": "ukrainian",
    "el": "greek",
    "ms": "malay",
    "cs": "czech",
    "ro": "romanian",
    "da": "danish",
    "hu": "hungarian",
    "ta": "tamil",
    "no": "norwegian",
    "th": "thai",
    "ur": "urdu",
    "hr": "croatian",
    "bg": "bulgarian",
    "lt": "lithuanian",
    "la": "latin",
    "mi": "maori",
    "ml": "malayalam",
    "cy": "welsh",
    "sk": "slovak",
    "te": "telugu",
    "fa": "persian",
    "lv": "latvian",
    "bn": "bengali",
    "sr": "serbian",
    "az": "azerbaijani",
    "sl": "slovenian",
    "kn": "kannada",
    "et": "estonian",
    "mk": "macedonian",
    "br": "breton",
    "eu": "basque",
    "is": "icelandic",
    "hy": "armenian",
    "ne": "nepali",
    "mn": "mongolian",
    "bs": "bosnian",
    "kk": "kazakh",
    "sq": "albanian",
    "sw": "swahili",
    "gl": "galician",
    "mr": "marathi",
    "pa": "punjabi",
    "si": "sinhala",
    "km": "khmer",
    "sn": "shona",
    "yo": "yoruba",
    "so": "somali",
    "af": "afrikaans",
    "oc": "occitan",
    "ka": "georgian",
    "be": "belarusian",
    "tg": "tajik",
    "sd": "sindhi",
    "gu": "gujarati",
    "am": "amharic",
    "yi": "yiddish",
    "lo": "lao",
    "uz": "uzbek",
    "fo": "faroese",
    "ht": "haitian creole",
    "ps": "pashto",
    "tk": "turkmen",
    "nn": "nynorsk",
    "mt": "maltese",
    "sa": "sanskrit",
    "lb": "luxembourgish",
    "my": "myanmar",
    "bo": "tibetan",
    "tl": "tagalog",
    "mg": "malagasy",
    "as": "assamese",
    "tt": "tatar",
    "haw": "hawaiian",
    "ln": "lingala",
    "ha": "hausa",
    "ba": "bashkir",
    "jw": "javanese",
    "su": "sundanese",
    "yue": "cantonese",
}


@dataclass()
class TranscriptionOptions:
    language: Optional[str] = None
    task: Task = Task.TRANSCRIBE
    model: TranscriptionModel = field(default_factory=TranscriptionModel)
    word_level_timings: bool = False
    temperature: Tuple[float, ...] = DEFAULT_WHISPER_TEMPERATURE
    initial_prompt: str = ""
    openai_access_token: str = field(
        default="", metadata=config(exclude=Exclude.ALWAYS)
    )


def humanize_language(language: str) -> str:
    if language == "":
        return _("Detect Language")
    return LANGUAGES[language].title()


@dataclass()
class FileTranscriptionOptions:
    file_paths: Optional[List[str]] = None
    url: Optional[str] = None
    output_formats: Set["OutputFormat"] = field(default_factory=set)


@dataclass_json
@dataclass
class FileTranscriptionTask:
    class Status(enum.Enum):
        QUEUED = "queued"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELED = "canceled"

    class Source(enum.Enum):
        FILE_IMPORT = "file_import"
        URL_IMPORT = "url_import"
        FOLDER_WATCH = "folder_watch"

    transcription_options: TranscriptionOptions
    file_transcription_options: FileTranscriptionOptions
    model_path: str
    # deprecated: use uid
    id: int = field(default_factory=lambda: randint(0, 100_000_000))
    uid: uuid.UUID = field(default_factory=uuid.uuid4)
    segments: List[Segment] = field(default_factory=list)
    status: Optional[Status] = None
    fraction_completed = 0.0
    error: Optional[str] = None
    queued_at: Optional[datetime.datetime] = None
    started_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    output_directory: Optional[str] = None
    source: Source = Source.FILE_IMPORT
    file_path: Optional[str] = None
    url: Optional[str] = None
    fraction_downloaded: float = 0.0


class OutputFormat(enum.Enum):
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"


class Stopped(Exception):
    pass


SUPPORTED_AUDIO_FORMATS = "Audio files (*.mp3 *.wav *.m4a *.ogg *.opus *.flac);;\
Video files (*.mp4 *.webm *.ogm *.mov *.mkv *.avi *.wmv);;All files (*.*)"


def get_output_file_path(
    file_path: str,
    task: Task,
    language: Optional[str],
    model: TranscriptionModel,
    output_format: OutputFormat,
    output_directory: str | None = None,
    export_file_name_template: str | None = None,
):
    input_file_name = os.path.splitext(os.path.basename(file_path))[0]
    date_time_now = datetime.datetime.now().strftime("%d-%b-%Y %H-%M-%S")

    export_file_name_template = (
        export_file_name_template
        if export_file_name_template is not None
        else Settings().get_default_export_file_template()
    )

    output_file_name = (
        export_file_name_template.replace("{{ input_file_name }}", input_file_name)
        .replace("{{ task }}", task.value)
        .replace("{{ language }}", language or "")
        .replace("{{ model_type }}", model.model_type.value)
        .replace(
            "{{ model_size }}",
            model.whisper_model_size.value
            if model.whisper_model_size is not None
            else "",
        )
        .replace("{{ date_time }}", date_time_now)
        + f".{output_format.value}"
    )

    output_directory = output_directory or os.path.dirname(file_path)
    return os.path.join(output_directory, output_file_name)
