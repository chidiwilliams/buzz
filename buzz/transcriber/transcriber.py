import datetime
import enum
import os
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
    id: int = field(default_factory=lambda: randint(0, 100_000_000))
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

    def status_text(self) -> str:
        match self.status:
            case FileTranscriptionTask.Status.IN_PROGRESS:
                if self.fraction_downloaded > 0 and self.fraction_completed == 0:
                    return f'{_("Downloading")} ({self.fraction_downloaded :.0%})'
                return f'{_("In Progress")} ({self.fraction_completed :.0%})'
            case FileTranscriptionTask.Status.COMPLETED:
                status = _("Completed")
                if self.started_at is not None and self.completed_at is not None:
                    status += f" ({self.format_timedelta(self.completed_at - self.started_at)})"
                return status
            case FileTranscriptionTask.Status.FAILED:
                return f'{_("Failed")} ({self.error})'
            case FileTranscriptionTask.Status.CANCELED:
                return _("Canceled")
            case FileTranscriptionTask.Status.QUEUED:
                return _("Queued")
            case _:
                return ""

    @staticmethod
    def format_timedelta(delta: datetime.timedelta):
        mm, ss = divmod(delta.seconds, 60)
        result = f"{ss}s"
        if mm == 0:
            return result
        hh, mm = divmod(mm, 60)
        result = f"{mm}m {result}"
        if hh == 0:
            return result
        return f"{hh}h {result}"


class OutputFormat(enum.Enum):
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"


class Stopped(Exception):
    pass


SUPPORTED_AUDIO_FORMATS = "Audio files (*.mp3 *.wav *.m4a *.ogg);;\
Video files (*.mp4 *.webm *.ogm *.mov);;All files (*.*)"


def get_output_file_path(task: FileTranscriptionTask, output_format: OutputFormat):
    input_file_name = os.path.splitext(os.path.basename(task.file_path))[0]
    date_time_now = datetime.datetime.now().strftime("%d-%b-%Y %H-%M-%S")

    export_file_name_template = Settings().value(
        Settings.Key.DEFAULT_EXPORT_FILE_NAME,
        "{{ input_file_name }} ({{ task }}d on {{ date_time }})",
    )

    output_file_name = (
        export_file_name_template.replace("{{ input_file_name }}", input_file_name)
        .replace("{{ task }}", task.transcription_options.task.value)
        .replace("{{ language }}", task.transcription_options.language or "")
        .replace("{{ model_type }}", task.transcription_options.model.model_type.value)
        .replace(
            "{{ model_size }}",
            task.transcription_options.model.whisper_model_size.value
            if task.transcription_options.model.whisper_model_size is not None
            else "",
        )
        .replace("{{ date_time }}", date_time_now)
        + f".{output_format.value}"
    )

    output_directory = task.output_directory or os.path.dirname(task.file_path)
    return os.path.join(output_directory, output_file_name)
