import logging
from typing import Union, Any, List

import numpy as np

from buzz import whisper_audio
from buzz.model_loader import LOADED_WHISPER_CPP_BINARY
from buzz.transcriber.transcriber import Segment, Task, TranscriptionOptions

if LOADED_WHISPER_CPP_BINARY:
    import _pywhispercpp as whisper_cpp


class WhisperCpp:
    def __init__(
        self,
        model: str,
        whisper_params: dict,
        new_segment_callback=None
    ) -> None:
        self.segments: List[Segment] = []
        self.ctx = whisper_cpp.whisper_init_from_file(model.encode())
        self.params = whisper_cpp.whisper_full_default_params(whisper_cpp.WHISPER_SAMPLING_GREEDY)
        self.set_params(whisper_params)

        if new_segment_callback:
            whisper_cpp.assign_new_segment_callback(self.params, new_segment_callback)

    def set_params(self, kwargs: dict) -> None:
        for param in kwargs:
            setattr(self.params, param, kwargs[param])

    def append_segment(self, txt: bytes, start: int, end: int):
        if txt == b'':
            return True

        try:
            self.segments.append(
                Segment(
                    start=start * 10,  # centisecond to ms
                    end=end * 10,  # centisecond to ms
                    text=txt.decode("utf-8"),
                )
            )

            return True
        except UnicodeDecodeError:
            return False

    def transcribe(self, audio: Union[np.ndarray, str], params: Any):
        self.segments = []
        if isinstance(audio, str):
            audio = whisper_audio.load_audio(audio)

        logging.debug("Loaded audio with length = %s", len(audio))

        result = whisper_cpp.whisper_full(
            self.ctx, self.params, audio, len(audio)
        )
        if result != 0:
            raise Exception(f"Error from whisper.cpp: {result}")

        n_segments = whisper_cpp.whisper_full_n_segments(self.ctx)

        if params.get("token_timestamps", False):
            # Will process word timestamps
            byte_buffer = b''
            txt_start = 0
            txt_end = 0

            for i in range(n_segments):
                # try-catch will guard against multi-byte utf-8 characters
                # https://github.com/ggerganov/whisper.cpp/issues/1798
                try:
                    txt = whisper_cpp.whisper_full_get_segment_text(self.ctx, i)
                    txt_as_bytes = txt.encode('utf-8')
                except UnicodeDecodeError as e:
                    txt_as_bytes = e.object

                start = whisper_cpp.whisper_full_get_segment_t0(self.ctx, i)
                end = whisper_cpp.whisper_full_get_segment_t1(self.ctx, i)

                if txt_as_bytes.startswith(b' ') and self.append_segment(byte_buffer, txt_start, txt_end):
                    byte_buffer = txt_as_bytes
                    txt_start = start
                    txt_end = end
                    continue

                if txt_as_bytes.startswith(b', '):
                    byte_buffer += b','
                    self.append_segment(byte_buffer, txt_start, txt_end)
                    byte_buffer = txt_as_bytes.lstrip(b',')
                    txt_start = start
                    txt_end = end
                    continue

                byte_buffer += txt_as_bytes
                txt_end = end

            # Append the last segment
            self.append_segment(byte_buffer, txt_start, txt_end)

        else:
            for i in range(n_segments):
                try:
                    txt = whisper_cpp.whisper_full_get_segment_text(self.ctx, i)
                    start = whisper_cpp.whisper_full_get_segment_t0(self.ctx, i)
                    end = whisper_cpp.whisper_full_get_segment_t1(self.ctx, i)

                    self.append_segment(txt.encode('utf-8'), start, end)
                except UnicodeDecodeError:
                    pass

        return {
            "segments": self.segments,
            "text": "".join([segment.text for segment in self.segments]),
        }

    def __del__(self):
        whisper_cpp.whisper_free(self.ctx)


def whisper_cpp_params(
    transcription_options: TranscriptionOptions,
    print_realtime=False,
    print_progress=False,
):
    params_dict = {
        "strategy": whisper_cpp.WHISPER_SAMPLING_GREEDY,
        "print_realtime": print_realtime,
        "print_progress": print_progress,
        "language": transcription_options.language or "en",
        "translate": transcription_options.task == Task.TRANSLATE,
        "max_len": 1 if transcription_options.word_level_timings else 0,
        "token_timestamps": transcription_options.word_level_timings,
        "initial_prompt": transcription_options.initial_prompt,
    }
    return params_dict
