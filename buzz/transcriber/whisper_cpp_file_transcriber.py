import ctypes
import logging
import sys
from typing import Optional, List

from PyQt6.QtCore import QObject

from buzz import whisper_audio
from buzz.model_loader import LOADED_WHISPER_CPP_BINARY
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment, Stopped
from buzz.transcriber.whisper_cpp import WhisperCpp, whisper_cpp_params

if LOADED_WHISPER_CPP_BINARY:
    from buzz import whisper_cpp


class WhisperCppFileTranscriber(FileTranscriber):
    duration_audio_ms = sys.maxsize  # max int
    state: "WhisperCppFileTranscriber.State"

    class State:
        running = True

    def __init__(
        self, task: FileTranscriptionTask, parent: Optional["QObject"] = None
    ) -> None:
        super().__init__(task, parent)

        self.language = task.transcription_options.language
        self.model_path = task.model_path
        self.task = task.transcription_options.task
        self.word_level_timings = task.transcription_options.word_level_timings
        self.state = self.State()

    def transcribe(self) -> List[Segment]:
        self.state.running = True
        model_path = self.model_path

        logging.debug(
            "Starting whisper_cpp file transcription, file path = %s, language = %s, "
            "task = %s, model_path = %s, word level timings = %s",
            self.transcription_task.file_path,
            self.language,
            self.task,
            model_path,
            self.word_level_timings,
        )

        audio = whisper_audio.load_audio(self.transcription_task.file_path)
        self.duration_audio_ms = len(audio) * 1000 / whisper_audio.SAMPLE_RATE

        whisper_params = whisper_cpp_params(
            language=self.language if self.language is not None else "",
            task=self.task,
            word_level_timings=self.word_level_timings,
        )
        whisper_params.encoder_begin_callback_user_data = ctypes.c_void_p(
            id(self.state)
        )
        whisper_params.encoder_begin_callback = (
            whisper_cpp.whisper_encoder_begin_callback(self.encoder_begin_callback)
        )
        whisper_params.new_segment_callback_user_data = ctypes.c_void_p(id(self.state))
        whisper_params.new_segment_callback = whisper_cpp.whisper_new_segment_callback(
            self.new_segment_callback
        )

        model = WhisperCpp(model=model_path)
        result = model.transcribe(
            audio=self.transcription_task.file_path, params=whisper_params
        )

        if not self.state.running:
            raise Stopped

        self.state.running = False
        return result["segments"]

    def new_segment_callback(self, ctx, _state, _n_new, user_data):
        n_segments = whisper_cpp.whisper_full_n_segments(ctx)
        t1 = whisper_cpp.whisper_full_get_segment_t1(ctx, n_segments - 1)
        # t1 seems to sometimes be larger than the duration when the
        # audio ends in silence. Trim to fix the displayed progress.
        progress = min(t1 * 10, self.duration_audio_ms)
        state: WhisperCppFileTranscriber.State = ctypes.cast(
            user_data, ctypes.py_object
        ).value
        if state.running:
            self.progress.emit((progress, self.duration_audio_ms))

    @staticmethod
    def encoder_begin_callback(_ctx, _state, user_data):
        state: WhisperCppFileTranscriber.State = ctypes.cast(
            user_data, ctypes.py_object
        ).value
        return state.running == 1

    def stop(self):
        self.state.running = False
