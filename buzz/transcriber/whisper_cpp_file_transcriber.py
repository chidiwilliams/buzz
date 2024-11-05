import ctypes
import logging
import sys
from typing import Optional, List

from PyQt6.QtCore import QObject

from buzz import whisper_audio
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment, Stopped
from buzz.transcriber.whisper_cpp import WhisperCpp


class WhisperCppFileTranscriber(FileTranscriber):
    duration_audio_ms = sys.maxsize  # max int
    state: "WhisperCppFileTranscriber.State"

    class State:
        running = True

    def __init__(
        self, task: FileTranscriptionTask, parent: Optional["QObject"] = None
    ) -> None:
        super().__init__(task, parent)

        self.transcription_options = task.transcription_options
        self.model_path = task.model_path
        self.model = WhisperCpp(model=self.model_path)
        self.state = self.State()

    def transcribe(self) -> List[Segment]:
        self.state.running = True

        logging.debug(
            "Starting whisper_cpp file transcription, file path = %s, language = %s, "
            "task = %s, model_path = %s, word level timings = %s",
            self.transcription_task.file_path,
            self.transcription_options.language,
            self.transcription_options.task,
            self.model_path,
            self.transcription_options.word_level_timings,
        )

        audio = whisper_audio.load_audio(self.transcription_task.file_path)
        self.duration_audio_ms = len(audio) * 1000 / whisper_audio.SAMPLE_RATE

        whisper_params = self.model.get_params(
            transcription_options=self.transcription_options
        )
        whisper_params.encoder_begin_callback_user_data = ctypes.c_void_p(
            id(self.state)
        )
        whisper_params.encoder_begin_callback = (
            self.model.get_instance().get_encoder_begin_callback(self.encoder_begin_callback)
        )
        whisper_params.new_segment_callback_user_data = ctypes.c_void_p(id(self.state))
        whisper_params.new_segment_callback = self.model.get_instance().get_new_segment_callback(
            self.new_segment_callback
        )

        result = self.model.transcribe(
            audio=self.transcription_task.file_path, params=whisper_params
        )

        if not self.state.running:
            raise Stopped

        self.state.running = False
        return result["segments"]

    def new_segment_callback(self, ctx, _state, _n_new, user_data):
        n_segments = self.model.get_instance().full_n_segments(ctx)
        t1 = self.model.get_instance().full_get_segment_t1(ctx, n_segments - 1)
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
