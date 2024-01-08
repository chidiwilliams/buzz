import datetime
import json
import logging
import multiprocessing
import sys
from multiprocessing.connection import Connection
from threading import Thread
from typing import Optional, List

import tqdm
from PyQt6.QtCore import QObject

from buzz import transformers_whisper
from buzz.conn import pipe_stderr
from buzz.model_loader import ModelType
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment

if sys.platform != "linux":
    import faster_whisper
    import whisper
    import stable_whisper


class WhisperFileTranscriber(FileTranscriber):
    """WhisperFileTranscriber transcribes an audio file to text, writes the text to a file, and then opens the file
    using the default program for opening txt files."""

    current_process: multiprocessing.Process
    running = False
    read_line_thread: Optional[Thread] = None
    READ_LINE_THREAD_STOP_TOKEN = "--STOP--"

    def __init__(
        self, task: FileTranscriptionTask, parent: Optional["QObject"] = None
    ) -> None:
        super().__init__(task, parent)
        self.segments = []
        self.started_process = False
        self.stopped = False

    def transcribe(self) -> List[Segment]:
        time_started = datetime.datetime.now()
        logging.debug(
            "Starting whisper file transcription, task = %s", self.transcription_task
        )

        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

        self.current_process = multiprocessing.Process(
            target=self.transcribe_whisper, args=(send_pipe, self.transcription_task)
        )
        if not self.stopped:
            self.current_process.start()
            self.started_process = True

        self.read_line_thread = Thread(target=self.read_line, args=(recv_pipe,))
        self.read_line_thread.start()

        self.current_process.join()

        if self.current_process.exitcode != 0:
            send_pipe.close()

        self.read_line_thread.join()

        logging.debug(
            "whisper process completed with code = %s, time taken = %s, number of segments = %s",
            self.current_process.exitcode,
            datetime.datetime.now() - time_started,
            len(self.segments),
        )

        if self.current_process.exitcode != 0:
            raise Exception("Unknown error")

        return self.segments

    @classmethod
    def transcribe_whisper(
        cls, stderr_conn: Connection, task: FileTranscriptionTask
    ) -> None:
        with pipe_stderr(stderr_conn):
            if task.transcription_options.model.model_type == ModelType.HUGGING_FACE:
                segments = cls.transcribe_hugging_face(task)
            elif (
                task.transcription_options.model.model_type == ModelType.FASTER_WHISPER
            ):
                segments = cls.transcribe_faster_whisper(task)
            elif task.transcription_options.model.model_type == ModelType.WHISPER:
                segments = cls.transcribe_openai_whisper(task)
            else:
                raise Exception(
                    f"Invalid model type: {task.transcription_options.model.model_type}"
                )

            segments_json = json.dumps(segments, ensure_ascii=True, default=vars)
            sys.stderr.write(f"segments = {segments_json}\n")
            sys.stderr.write(WhisperFileTranscriber.READ_LINE_THREAD_STOP_TOKEN + "\n")

    @classmethod
    def transcribe_hugging_face(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = transformers_whisper.load_model(task.model_path)
        language = (
            task.transcription_options.language
            if task.transcription_options.language is not None
            else "en"
        )
        result = model.transcribe(
            audio=task.file_path,
            language=language,
            task=task.transcription_options.task.value,
            verbose=False,
        )
        return [
            Segment(
                start=int(segment.get("start") * 1000),
                end=int(segment.get("end") * 1000),
                text=segment.get("text"),
            )
            for segment in result.get("segments")
        ]

    @classmethod
    def transcribe_faster_whisper(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = faster_whisper.WhisperModel(
            model_size_or_path=task.transcription_options.model.whisper_model_size.to_faster_whisper_model_size()
        )
        whisper_segments, info = model.transcribe(
            audio=task.file_path,
            language=task.transcription_options.language,
            task=task.transcription_options.task.value,
            temperature=task.transcription_options.temperature,
            initial_prompt=task.transcription_options.initial_prompt,
            word_timestamps=task.transcription_options.word_level_timings,
        )
        segments = []
        with tqdm.tqdm(total=round(info.duration, 2), unit=" seconds") as pbar:
            for segment in list(whisper_segments):
                # Segment will contain words if word-level timings is True
                if segment.words:
                    for word in segment.words:
                        segments.append(
                            Segment(
                                start=int(word.start * 1000),
                                end=int(word.end * 1000),
                                text=word.word,
                            )
                        )
                else:
                    segments.append(
                        Segment(
                            start=int(segment.start * 1000),
                            end=int(segment.end * 1000),
                            text=segment.text,
                        )
                    )

                pbar.update(segment.end - segment.start)
        return segments

    @classmethod
    def transcribe_openai_whisper(cls, task: FileTranscriptionTask) -> List[Segment]:
        model = whisper.load_model(task.model_path)

        if task.transcription_options.word_level_timings:
            stable_whisper.modify_model(model)
            result = model.transcribe(
                audio=task.file_path,
                language=task.transcription_options.language,
                task=task.transcription_options.task.value,
                temperature=task.transcription_options.temperature,
                initial_prompt=task.transcription_options.initial_prompt,
                pbar=True,
            )
            segments = stable_whisper.group_word_timestamps(result)
            return [
                Segment(
                    start=int(segment.get("start") * 1000),
                    end=int(segment.get("end") * 1000),
                    text=segment.get("text"),
                )
                for segment in segments
            ]

        result = model.transcribe(
            audio=task.file_path,
            language=task.transcription_options.language,
            task=task.transcription_options.task.value,
            temperature=task.transcription_options.temperature,
            initial_prompt=task.transcription_options.initial_prompt,
            verbose=False,
        )
        segments = result.get("segments")
        return [
            Segment(
                start=int(segment.get("start") * 1000),
                end=int(segment.get("end") * 1000),
                text=segment.get("text"),
            )
            for segment in segments
        ]

    def stop(self):
        self.stopped = True
        if self.started_process:
            self.current_process.terminate()

    def read_line(self, pipe: Connection):
        while True:
            try:
                line = pipe.recv().strip()
            except EOFError:  # Connection closed
                break

            if line == self.READ_LINE_THREAD_STOP_TOKEN:
                return

            if line.startswith("segments = "):
                segments_dict = json.loads(line[11:])
                segments = [
                    Segment(
                        start=segment.get("start"),
                        end=segment.get("end"),
                        text=segment.get("text"),
                    )
                    for segment in segments_dict
                ]
                self.segments = segments
            else:
                try:
                    progress = int(line.split("|")[0].strip().strip("%"))
                    self.progress.emit((progress, 100))
                except ValueError:
                    logging.debug("whisper (stderr): %s", line)
                    continue
