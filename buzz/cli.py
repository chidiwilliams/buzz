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
    parser.addPositionalArgument("<command>", "One of the following commands:\n- add\n- rename")
    parser.parse(app.arguments())

    args = parser.positionalArguments()
    if len(args) == 0:
        parser.addHelpOption()
        parser.addVersionOption()

        parser.process(app)
        return

    command = args[0]
    if command == "rename":
        return _parse_rename(app, parser)
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
        extract_speech_option = QCommandLineOption(
            ["e", "extract-speech"], "Extract speech from audio before transcribing."
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
                extract_speech_option,
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
        extract_speech = parser.isSet(extract_speech_option)

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
            extract_speech=extract_speech,
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


def _parse_rename(app: Application, parser: QCommandLineParser):
    """Bulk-rename audio files in a folder based on transcribed first words.

    Usage::

        buzz rename --model-type whispercpp --model-size small ./folder
        buzz rename --dry-run ./folder
        buzz rename --undo ./folder/.undo_20260505_142315.json
    """
    # Lazy imports — keep CLI startup fast and avoid pulling heavy deps
    # for unrelated commands.
    from datetime import datetime
    from pathlib import Path
    import sys as _sys

    from buzz.transcriber.bulk_renamer import (
        BulkRenamer,
        RenamerConfig,
        apply_plan,
        undo_from_log,
    )

    parser.clearPositionalArguments()
    parser.addPositionalArgument("folder", "Audio folder to rename")

    model_type_option = QCommandLineOption(
        ["m", "model-type"],
        f"Model type. Allowed: {join_values(CommandLineModelType)}. "
        f"Default: {CommandLineModelType.WHISPER_CPP.value}.",
        "model-type",
        CommandLineModelType.WHISPER_CPP.value,
    )
    model_size_option = QCommandLineOption(
        ["s", "model-size"],
        f"Model size. Allowed: {join_values(WhisperModelSize)}. "
        f"Default: {WhisperModelSize.TINY.value}.",
        "model-size",
        WhisperModelSize.TINY.value,
    )
    language_option = QCommandLineOption(
        ["l", "language"],
        "Language code (e.g. en, fr). Empty = auto-detect.",
        "language",
        "en",
    )
    trim_option = QCommandLineOption(
        ["trim"],
        "Seconds of audio to transcribe per file. Default: 5.",
        "trim",
        "5",
    )
    words_option = QCommandLineOption(
        ["words"],
        "Number of leading words to use for the new filename. Default: 6.",
        "words",
        "6",
    )
    keep_prefix_option = QCommandLineOption(
        ["keep-prefix"],
        "Preserve a leading 'NN_' or 'NN-' from the original filename.",
    )
    dry_run_option = QCommandLineOption(
        ["n", "dry-run"],
        "Show planned renames without applying.",
    )
    undo_option = QCommandLineOption(
        ["undo"],
        "Reverse a previous batch using its JSON log path.",
        "undo",
        "",
    )
    parser.addOptions([
        model_type_option, model_size_option, language_option,
        trim_option, words_option, keep_prefix_option,
        dry_run_option, undo_option,
    ])
    parser.addHelpOption()
    parser.process(app)

    # Undo path — no model needed, no app run
    undo_path = parser.value(undo_option)
    if undo_path:
        result = undo_from_log(Path(undo_path))
        print(f"Reverted: {result['reverted_count']}, "
              f"failed: {result['failed_count']}")
        if not result["failed"]:
            _sys.exit(0)
        for entry, why in result["failed"]:
            print(f"  failed: {entry['from']} -> {entry['to']}: {why}")
        _sys.exit(1)

    args = parser.positionalArguments()
    if len(args) < 2:
        raise CommandLineError("rename: folder argument is required")
    folder = Path(args[1])
    if not folder.is_dir():
        raise CommandLineError(f"rename: not a directory: {folder}")

    cli_model_type = parse_enum_option(model_type_option, parser, CommandLineModelType)
    model_type = ModelType[cli_model_type.name]
    model_size = parse_enum_option(model_size_option, parser, WhisperModelSize)
    model = TranscriptionModel(model_type=model_type, whisper_model_size=model_size)
    language = parser.value(language_option) or None

    try:
        trim_seconds = float(parser.value(trim_option))
        first_words = int(parser.value(words_option))
    except ValueError:
        raise CommandLineError("rename: --trim and --words must be numeric")

    # Resolve the model path. We use ModelDownloader synchronously here
    # rather than via QThreadPool because the CLI doesn't have a UI thread.
    print(f"Resolving model: {model_type.value}/{model_size.value}…", file=_sys.stderr)
    downloader = ModelDownloader(model=model)
    model_path: list = []  # captured by callback

    def _on_finished(path):
        model_path.append(path)

    def _on_error(err):
        raise CommandLineError(f"Model download failed: {err}")

    downloader.signals.finished.connect(_on_finished)
    downloader.signals.error.connect(_on_error)
    downloader.run()  # synchronous in CLI
    if not model_path:
        raise CommandLineError("Model download did not produce a path")

    transcription_options = TranscriptionOptions(
        language=language,
        task=Task.TRANSCRIBE,
        model=model,
        word_level_timings=False,
        extract_speech=False,
    )
    cfg = RenamerConfig(
        transcription_options=transcription_options,
        model_path=model_path[0],
        trim_seconds=trim_seconds,
        first_words=first_words,
        keep_numeric_prefix=parser.isSet(keep_prefix_option),
    )

    renamer = BulkRenamer(cfg)
    state = {"done": 0, "total": 0}

    def _progress(done, total, _plan):
        state["done"], state["total"] = done, total
        bar = ("#" * (40 * done // total)).ljust(40) if total else "-" * 40
        _sys.stderr.write(f"\r  [{bar}] {done}/{total}")
        _sys.stderr.flush()

    def _log(msg, level):
        if level in ("warn", "error"):
            _sys.stderr.write(f"\n  [{level}] {msg}\n")

    renamer.progress.connect(_progress)
    renamer.log.connect(_log)
    plans = renamer.plan_renames(folder)
    _sys.stderr.write("\n")

    print(f"\nPlanned renames in {folder}:")
    for plan in plans:
        if plan.status == "ready" and plan.will_change:
            print(f"  {plan.original_path.name}  ->  {plan.proposed_path.name}")
        elif plan.status == "ready":
            print(f"  {plan.original_path.name}  (already correctly named)")
        elif plan.status == "skipped":
            print(f"  {plan.original_path.name}  SKIP ({plan.error})")
        else:
            print(f"  {plan.original_path.name}  ERROR ({plan.error})")

    if parser.isSet(dry_run_option):
        print("\n(dry run; no changes applied)")
        _sys.exit(0)

    to_apply = sum(1 for p in plans if p.will_change)
    if to_apply == 0:
        print("\nNothing to rename.")
        _sys.exit(0)

    print(f"\nReady to apply {to_apply} rename(s).")
    resp = input("Proceed? [y/N] ").strip().lower()
    if resp != "y":
        print("Aborted.")
        _sys.exit(0)

    log_path = folder / f".undo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary = apply_plan(plans, log_path)
    print(f"\nApplied: {summary['applied_count']}")
    print(f"Skipped: {summary['skipped_count']}")
    print(f"Errors:  {summary['error_count']}")
    print(f"Undo log: {log_path}")
    print(f"  Undo with: buzz rename --undo {log_path}")
    _sys.exit(0)
