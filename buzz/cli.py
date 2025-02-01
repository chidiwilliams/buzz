import enum
import sys
import typing
import urllib.parse

from PyQt6.QtCore import QCommandLineParser, QCommandLineOption

from buzz.model_loader import (
    ModelType,
    WhisperModelSize,
    TranscriptionModel,
    ModelDownloader,
)
from buzz.store.keyring_store import get_password, Key
from buzz.transcriber.transcriber import (
    Task,
    FileTranscriptionTask,
    FileTranscriptionOptions,
    TranscriptionOptions,
    LANGUAGES,
    OutputFormat,
)
from buzz.widgets.application import Application


class CommandLineError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class CommandLineModelType(enum.Enum):
    WHISPER = "whisper"
    WHISPER_CPP = "whispercpp"
    HUGGING_FACE = "huggingface"
    FASTER_WHISPER = "fasterwhisper"
    OPEN_AI_WHISPER_API = "openaiapi"


def parse_command_line(app: Application):
    parser = QCommandLineParser()
    try:
        parse(app, parser)
    except CommandLineError as exc:
        print(f"Error: {str(exc)}\n", file=sys.stderr)
        print(parser.helpText())
        sys.exit(1)

def is_url(path: str) -> bool:
    parsed = urllib.parse.urlparse(path)
    return all([parsed.scheme, parsed.netloc])

def parse(app: Application, parser: QCommandLineParser):
    parser.addPositionalArgument("<command>", "One of the following commands:\n- add")
    parser.parse(app.arguments())

    args = parser.positionalArguments()
    if len(args) == 0:
        parser.addHelpOption()
        parser.addVersionOption()

        parser.process(app)
        return

    command = args[0]
    if command == "add":
        parser.clearPositionalArguments()

        parser.addPositionalArgument("files", "Input file paths", "[file file file...]")

        task_option = QCommandLineOption(
            ["t", "task"],
            f"The task to perform. Allowed: {join_values(Task)}. Default: {Task.TRANSCRIBE.value}.",
            "task",
            Task.TRANSCRIBE.value,
        )
        model_type_option = QCommandLineOption(
            ["m", "model-type"],
            f"Model type. Allowed: {join_values(CommandLineModelType)}. Default: {CommandLineModelType.WHISPER.value}.",
            "model-type",
            CommandLineModelType.WHISPER.value,
        )
        model_size_option = QCommandLineOption(
            ["s", "model-size"],
            f"Model size. Use only when --model-type is whisper, whispercpp, or fasterwhisper. Allowed: {join_values(WhisperModelSize)}. Default: {WhisperModelSize.TINY.value}.",
            "model-size",
            WhisperModelSize.TINY.value,
        )
        hugging_face_model_id_option = QCommandLineOption(
            ["hfid"],
            'Hugging Face model ID. Use only when --model-type is huggingface. Example: "openai/whisper-tiny"',
            "id",
        )
        language_option = QCommandLineOption(
            ["l", "language"],
            f'Language code. Allowed: {", ".join(sorted([k + " (" + LANGUAGES[k].title() + ")" for k in LANGUAGES]))}. Leave empty to detect language.',
            "code",
            "",
        )
        initial_prompt_option = QCommandLineOption(
            ["p", "prompt"], "Initial prompt.", "prompt", ""
        )
        word_timestamp_option = QCommandLineOption(
            ["w", "word-timestamps"], "Generate word-level timestamps."
        )
        open_ai_access_token_option = QCommandLineOption(
            "openai-token",
            f"OpenAI access token. Use only when --model-type is {CommandLineModelType.OPEN_AI_WHISPER_API.value}. Defaults to your previously saved access token, if one exists.",
            "token",
        )
        output_directory_option = QCommandLineOption(
            ["d", "output-directory"], "Output directory", "directory"
        )
        srt_option = QCommandLineOption(["srt"], "Output result in an SRT file.")
        vtt_option = QCommandLineOption(["vtt"], "Output result in a VTT file.")
        txt_option = QCommandLineOption("txt", "Output result in a TXT file.")
        hide_gui_option = QCommandLineOption("hide-gui", "Hide the main application window.")

        parser.addOptions(
            [
                task_option,
                model_type_option,
                model_size_option,
                hugging_face_model_id_option,
                language_option,
                initial_prompt_option,
                word_timestamp_option,
                open_ai_access_token_option,
                output_directory_option,
                srt_option,
                vtt_option,
                txt_option,
                hide_gui_option,
            ]
        )

        parser.addHelpOption()
        parser.addVersionOption()

        parser.process(app)

        # slice after first argument, the command
        file_paths = parser.positionalArguments()[1:]
        if len(file_paths) == 0:
            raise CommandLineError("No input files")

        task = parse_enum_option(task_option, parser, Task)

        model_type = parse_enum_option(model_type_option, parser, CommandLineModelType)
        model_size = parse_enum_option(model_size_option, parser, WhisperModelSize)

        hugging_face_model_id = parser.value(hugging_face_model_id_option)

        if (
            hugging_face_model_id == ""
            and model_type == CommandLineModelType.HUGGING_FACE
        ):
            raise CommandLineError(
                "--hfid is required when --model-type is huggingface"
            )

        model = TranscriptionModel(
            model_type=ModelType[model_type.name],
            whisper_model_size=model_size,
            hugging_face_model_id=hugging_face_model_id,
        )
        ModelDownloader(model=model).run()
        model_path = model.get_local_model_path()

        if model_path is None:
            raise CommandLineError("Model not found")

        language = parser.value(language_option)
        if language == "":
            language = None
        elif LANGUAGES.get(language) is None:
            raise CommandLineError("Invalid language option")

        initial_prompt = parser.value(initial_prompt_option)

        word_timestamps = parser.isSet(word_timestamp_option)

        output_formats: typing.Set[OutputFormat] = set()
        if parser.isSet(srt_option):
            output_formats.add(OutputFormat.SRT)
        if parser.isSet(vtt_option):
            output_formats.add(OutputFormat.VTT)
        if parser.isSet(txt_option):
            output_formats.add(OutputFormat.TXT)

        openai_access_token = parser.value(open_ai_access_token_option)
        if (
            model.model_type == ModelType.OPEN_AI_WHISPER_API
            and openai_access_token == ""
        ):
            openai_access_token = get_password(key=Key.OPENAI_API_KEY)

            if openai_access_token == "":
                raise CommandLineError("No OpenAI access token found")

        output_directory = parser.value(output_directory_option)

        transcription_options = TranscriptionOptions(
            model=model,
            task=task,
            language=language,
            initial_prompt=initial_prompt,
            word_level_timings=word_timestamps,
            openai_access_token=openai_access_token,
        )

        for file_path in file_paths:
            path_is_url = is_url(file_path)

            file_transcription_options = FileTranscriptionOptions(
                file_paths=[file_path] if not path_is_url else None,
                url=file_path if path_is_url else None,
                output_formats=output_formats,
            )

            transcription_task = FileTranscriptionTask(
                file_path=file_path if not path_is_url else None,
                url=file_path if path_is_url else None,
                source=FileTranscriptionTask.Source.FILE_IMPORT if not path_is_url else FileTranscriptionTask.Source.URL_IMPORT,
                model_path=model_path,
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                output_directory=output_directory if output_directory != "" else None,
            )
            app.add_task(transcription_task, quit_on_complete=True)

        if parser.isSet(hide_gui_option):
            app.hide_main_window = True

T = typing.TypeVar("T", bound=enum.Enum)


def parse_enum_option(
    option: QCommandLineOption, parser: QCommandLineParser, enum_class: typing.Type[T]
) -> T:
    try:
        return enum_class(parser.value(option))
    except ValueError:
        raise CommandLineError(f"Invalid value for --{option.names()[-1]} option.")


def join_values(enum_class: typing.Type[enum.Enum]) -> str:
    return ", ".join([v.value for v in enum_class])
