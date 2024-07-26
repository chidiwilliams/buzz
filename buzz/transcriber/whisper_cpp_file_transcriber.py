import logging
import datetime
import json
import sys
import multiprocessing
from multiprocessing.connection import Connection
from threading import Thread

from typing import Optional, List

from PyQt6.QtCore import QObject

from buzz import whisper_audio
from buzz.conn import pipe_stderr
from buzz.model_loader import LOADED_WHISPER_CPP_BINARY
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment, Stopped
from buzz.transcriber.whisper_cpp import WhisperCpp, whisper_cpp_params

if LOADED_WHISPER_CPP_BINARY:
    import _pywhispercpp as whisper_cpp


class WhisperCppFileTranscriber(FileTranscriber):
    duration_audio_ms = sys.maxsize  # max int
    state: "WhisperCppFileTranscriber.State"
    current_process: multiprocessing.Process
    read_line_thread: Thread

    class State:
        running = True

    def __init__(
        self, task: FileTranscriptionTask, parent: Optional["QObject"] = None
    ) -> None:
        super().__init__(task, parent)

        self.transcription_options = task.transcription_options
        self.model_path = task.model_path
        self.state = self.State()
        self.segments = []
        self.started_process = False
        self.stopped = False

    def transcribe(self) -> List[Segment]:
        time_started = datetime.datetime.now()
        self.state.running = True
        model_path = self.model_path

        logging.debug(
            "Starting whisper_cpp file transcription, file path = %s, language = %s, "
            "task = %s, model_path = %s, word level timings = %s",
            self.transcription_task.file_path,
            self.transcription_options.language,
            self.transcription_options.task,
            model_path,
            self.transcription_options.word_level_timings,
        )

        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

        self.current_process = multiprocessing.Process(
            target=self.run_transcription, args=(send_pipe, self.transcription_task)
        )
        if not self.stopped:
            self.current_process.start()
            self.started_process = True

        self.read_line_thread = Thread(target=self.read_line, args=(recv_pipe,))
        self.read_line_thread.start()

        self.current_process.join()
        send_pipe.close()

        self.read_line_thread.join()

        logging.debug(
            "whisper process completed with code = %s, time taken = %s,"
            " number of segments = %s",
            self.current_process.exitcode,
            datetime.datetime.now() - time_started,
            len(self.segments),
        )

        # Event if successful whisper_cpp tends to have exit code -11
        if self.current_process.exitcode != 0 and self.current_process.exitcode != -11:
            raise Exception("Unknown error")

        if not self.state.running:
            raise Stopped

        self.state.running = False

        return self.segments

    @classmethod
    def run_transcription(
            cls, stderr_conn: Connection, task: FileTranscriptionTask
    ) -> None:
        cls.stderr_conn = stderr_conn

        audio = whisper_audio.load_audio(task.file_path)
        cls.duration_audio_ms = len(audio) * 1000 / whisper_audio.SAMPLE_RATE

        whisper_params = whisper_cpp_params(
            transcription_options=task.transcription_options
        )

        model = WhisperCpp(
            model=task.model_path,
            whisper_params=whisper_cpp_params(
                transcription_options=task.transcription_options
            ),
            new_segment_callback=cls.new_segment_callback
        )
        result = model.transcribe(
            audio=task.file_path, params=whisper_params
        )

        with pipe_stderr(cls.stderr_conn):
            segments_json = json.dumps(result["segments"], ensure_ascii=True, default=vars)
            sys.stderr.write(f"segments = {segments_json}\n")
            sys.stderr.write(cls.READ_LINE_THREAD_STOP_TOKEN + "\n")

    @classmethod
    def new_segment_callback(cls, ctx, n_new, user_data):
        with pipe_stderr(cls.stderr_conn):
            n_segments = whisper_cpp.whisper_full_n_segments(ctx)
            t1 = whisper_cpp.whisper_full_get_segment_t1(ctx, n_segments - 1)
            # t1 seems to sometimes be larger than the duration when the
            # audio ends in silence. Trim to fix the displayed progress.
            progress = min(t1 * 10, cls.duration_audio_ms)

            sys.stderr.write(f"{round(progress / cls.duration_audio_ms * 100)}%\n")

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
                        translation=""
                    )
                    for segment in segments_dict
                ]

                self.segments = segments
            else:
                try:
                    match = self.PROGRESS_REGEX.search(line)
                    if match is not None:
                        progress = int(match.group().strip("%"))
                        self.progress.emit((progress, 100))
                except ValueError:
                    logging.debug("whisper (stderr): %s", line)
                    continue

    def stop(self):
        self.state.running = False

        self.stopped = True
        if self.started_process:
            self.current_process.terminate()
