import json
import logging
import multiprocessing
import os
import sys
from copy import copy
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path

import click
from appdirs import user_log_dir
from tqdm import tqdm

from buzz.model_loader import (
    ModelLoader,
    ModelType,
    TranscriptionModel,
    WhisperModelSize,
)
from buzz.transcriber import (
    Device,
    FileTranscriptionOptions,
    FileTranscriptionTask,
    OutputFormat,
    Segment,
    Task,
    TranscriptionOptions,
    WhisperFileTranscriber,
    get_default_output_file_path,
    transcribe_whisper,
    write_output,
)


class EnumType(click.Choice):
    """https://github.com/pallets/click/issues/605#issuecomment-901099036"""

    def __init__(self, enum, case_sensitive=False):
        self.__enum = enum
        super().__init__(
            choices=[item.value for item in enum], case_sensitive=case_sensitive
        )

    def convert(self, value, param, ctx):
        converted_str = super().convert(value, param, ctx)
        return self.__enum(converted_str)


class DataClassJSONEncoder(json.JSONEncoder):
    KEY = "_dataclass"

    def default(self, o):
        if is_dataclass(o):
            od = copy(o.__dict__)
            od[self.KEY] = o.__class__.__name__
            return od
        return super().default(o)


@click.group()
def cli():
    pass


@cli.command()
@click.option("-t", "--model_type", type=EnumType(ModelType), default="Whisper")
@click.option(
    "-s",
    "--model_size",
    "whisper_model_size",
    type=EnumType(WhisperModelSize),
    default="tiny",
)
@click.option("-I", "--model_id", "hugging_face_model_id")
@click.option("-d", "--device", type=EnumType(Device), default="cpu")
@click.option("-l", "--language", default="en")
@click.option("-w", "--word_level_timing", is_flag=True)
@click.option("-i", "--file_path", type=click.Path())
@click.option("-F", "--output_format", type=EnumType(OutputFormat), default="srt")
@click.option("-J", "--write_json", is_flag=True)
def transcribe(
    model_type,
    whisper_model_size,
    hugging_face_model_id,
    device,
    language,
    word_level_timing,
    file_path,
    output_format,
    write_json,
):
    model_option = TranscriptionModel(
        model_type=model_type,
        whisper_model_size=whisper_model_size,
        hugging_face_model_id=hugging_face_model_id,
    )
    option = TranscriptionOptions(
        language=language,
        task=Task.TRANSCRIBE,
        model=model_option,
        device=device,
        word_level_timings=word_level_timing,
    )

    with tqdm(desc="Downloading Model") as bar:
        # buzz/tests/model_loader.py:get_model_path
        model_loader = ModelLoader(model=model_option)
        model_path = ""

        def on_download_model_progress(progress):
            (current_size, total_size) = progress
            bar.total = total_size
            bar.update(current_size)

        def on_load_model(path: str):
            nonlocal model_path
            model_path = path

        model_loader.progress.connect(on_download_model_progress)
        model_loader.finished.connect(on_load_model)
        model_loader.run()
        logging.info("model path: %s", model_path)

    with tqdm(desc="Transcribing", total=100) as bar:
        # buzz/buzz/transcriber.py:WhisperFileTranscriber:run
        task = FileTranscriptionTask(
            file_path, option, FileTranscriptionOptions([file_path]), model_path
        )

        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)
        transcribe_process = multiprocessing.Process(
            target=transcribe_whisper, args=(send_pipe, task)
        )

        time_started = datetime.now()
        transcribe_process.start()
        while True:
            # buzz/buzz/transcriber.py:WhisperFileTranscriber:read_line
            try:
                line = recv_pipe.recv().strip()
            except EOFError:  # Connection closed
                break

            if line == WhisperFileTranscriber.READ_LINE_THREAD_STOP_TOKEN:
                break

            if line.startswith("segments = "):
                segments_dict = json.loads(line[11:])
                task.segments = [
                    Segment(
                        start=segment.get("start"),
                        end=segment.get("end"),
                        text=segment.get("text"),
                    )
                    for segment in segments_dict
                ]
            else:
                try:
                    progress = float(line.split("|")[0].strip().strip("%"))
                    logging.debug("update progress %f", progress)
                    bar.n = bar.last_print_n = progress
                    bar.update(0)
                except ValueError:
                    logging.debug("whisper (stderr): %s", line)
                    continue

        transcribe_process.join()
        if transcribe_process.exitcode != 0:
            send_pipe.close()

    logging.info(
        "whisper process completed with code = %s, time taken = %s, number of segments = %s",
        transcribe_process.exitcode,
        datetime.now() - time_started,
        len(task.segments),
    )

    output_file_path = Path(
        get_default_output_file_path(
            task=task.transcription_options.task,
            input_file_path=task.file_path,
            output_format=output_format,
        )
    )

    logging.info("writing subtitle to %s", output_file_path)
    write_output(
        path=output_file_path,
        segments=task.segments,
        should_open=True,
        output_format=output_format,
    )

    if write_json:
        output_json_path = output_file_path.with_suffix(".json")
        logging.info("writing segments RAW json to %s", output_file_path)
        with output_json_path.open("w") as f:
            json.dump(task.segments, f, cls=DataClassJSONEncoder, ensure_ascii=False)


@cli.command()
def translate():
    pass


if __name__ == "__main__":
    log_dir = user_log_dir(appname="Buzz")
    os.makedirs(log_dir, exist_ok=True)
    logfile = os.path.join(log_dir, "logs-cli.txt")
    logging.basicConfig(
        filename=logfile,
        level=logging.DEBUG,
        format="[%(asctime)s] %(module)s.%(funcName)s:%(lineno)d %(levelname)s -> %(message)s",
        force=True,
    )
    sys.exit(cli())
