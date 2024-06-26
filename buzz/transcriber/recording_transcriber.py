import datetime
import logging
import sys
import os
import wave
import tempfile
import threading
from typing import Optional

import torch
import numpy as np
import sounddevice
from sounddevice import PortAudioError
from openai import OpenAI
from PyQt6.QtCore import QObject, pyqtSignal

from buzz import transformers_whisper, whisper_audio
from buzz.model_loader import WhisperModelSize, ModelType, get_custom_api_whisper_model
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import TranscriptionOptions, Task
from buzz.transcriber.whisper_cpp import WhisperCpp, whisper_cpp_params
from buzz.transformers_whisper import TransformersWhisper

import whisper
import faster_whisper


class RecordingTranscriber(QObject):
    transcription = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    is_running = False
    SAMPLE_RATE = whisper_audio.SAMPLE_RATE
    MAX_QUEUE_SIZE = 10

    def __init__(
        self,
        transcription_options: TranscriptionOptions,
        input_device_index: Optional[int],
        sample_rate: int,
        model_path: str,
        sounddevice: sounddevice,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.transcription_options = transcription_options
        self.current_stream = None
        self.input_device_index = input_device_index
        self.sample_rate = sample_rate if sample_rate is not None else whisper_audio.SAMPLE_RATE
        self.model_path = model_path
        self.n_batch_samples = 5 * self.sample_rate  # every 5 seconds
        # pause queueing if more than 3 batches behind
        self.max_queue_size = 3 * self.n_batch_samples
        self.queue = np.ndarray([], dtype=np.float32)
        self.mutex = threading.Lock()
        self.sounddevice = sounddevice
        self.openai_client = None
        self.whisper_api_model = get_custom_api_whisper_model("")

    def start(self):
        model_path = self.model_path
        keep_samples = int(0.15 * self.sample_rate)

        if self.transcription_options.model.model_type == ModelType.WHISPER:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = whisper.load_model(model_path, device=device)
        elif self.transcription_options.model.model_type == ModelType.WHISPER_CPP:
            model = WhisperCpp(model_path)
        elif self.transcription_options.model.model_type == ModelType.FASTER_WHISPER:
            model = faster_whisper.WhisperModel(model_path)

            # Fix for large-v3 https://github.com/guillaumekln/faster-whisper/issues/547#issuecomment-1797962599
            if self.transcription_options.model.whisper_model_size == WhisperModelSize.LARGEV3:
                model.feature_extractor.mel_filters = model.feature_extractor.get_mel_filters(
                    model.feature_extractor.sampling_rate, model.feature_extractor.n_fft, n_mels=128
                )
        elif self.transcription_options.model.model_type == ModelType.OPEN_AI_WHISPER_API:
            settings = Settings()
            custom_openai_base_url = settings.value(
                key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
            )
            self.whisper_api_model = get_custom_api_whisper_model(custom_openai_base_url)
            self.openai_client = OpenAI(
                api_key=self.transcription_options.openai_access_token,
                base_url=custom_openai_base_url if custom_openai_base_url else None
            )
            logging.debug("Will use whisper API on %s, %s",
                          custom_openai_base_url, self.whisper_api_model)
        else:  # ModelType.HUGGING_FACE
            model = TransformersWhisper(model_path)

        initial_prompt = self.transcription_options.initial_prompt

        logging.debug(
            "Recording, transcription options = %s, model path = %s, sample rate = %s, device = %s",
            self.transcription_options,
            model_path,
            self.sample_rate,
            self.input_device_index,
        )

        self.is_running = True
        try:
            with self.sounddevice.InputStream(
                samplerate=self.sample_rate,
                device=self.input_device_index,
                dtype="float32",
                channels=1,
                callback=self.stream_callback,
            ):
                while self.is_running:
                    self.mutex.acquire()
                    if self.queue.size >= self.n_batch_samples:
                        samples = self.queue[: self.n_batch_samples]
                        self.queue = self.queue[self.n_batch_samples - keep_samples:]
                        self.mutex.release()

                        logging.debug(
                            "Processing next frame, sample size = %s, queue size = %s, amplitude = %s",
                            samples.size,
                            self.queue.size,
                            self.amplitude(samples),
                        )
                        time_started = datetime.datetime.now()

                        if (
                            self.transcription_options.model.model_type
                            == ModelType.WHISPER
                        ):
                            assert isinstance(model, whisper.Whisper)
                            result = model.transcribe(
                                audio=samples,
                                language=self.transcription_options.language,
                                task=self.transcription_options.task.value,
                                initial_prompt=initial_prompt,
                                temperature=self.transcription_options.temperature,
                            )
                        elif (
                            self.transcription_options.model.model_type
                            == ModelType.WHISPER_CPP
                        ):
                            assert isinstance(model, WhisperCpp)
                            result = model.transcribe(
                                audio=samples,
                                params=whisper_cpp_params(
                                    transcription_options=self.transcription_options
                                ),
                            )
                        elif (
                                self.transcription_options.model.model_type
                                == ModelType.FASTER_WHISPER
                        ):
                            assert isinstance(model, faster_whisper.WhisperModel)
                            whisper_segments, info = model.transcribe(
                                audio=samples,
                                language=self.transcription_options.language
                                if self.transcription_options.language != ""
                                else None,
                                task=self.transcription_options.task.value,
                                temperature=self.transcription_options.temperature,
                                initial_prompt=self.transcription_options.initial_prompt,
                                word_timestamps=self.transcription_options.word_level_timings,
                            )
                            result = {"text": " ".join([segment.text for segment in whisper_segments])}
                        elif (
                                self.transcription_options.model.model_type
                                == ModelType.HUGGING_FACE
                        ):
                            assert isinstance(model, TransformersWhisper)
                            result = model.transcribe(
                                audio=samples,
                                language=self.transcription_options.language
                                if self.transcription_options.language is not None
                                else "en",
                                task=self.transcription_options.task.value,
                            )
                        else:  # OPEN_AI_WHISPER_API
                            assert self.openai_client is not None
                            # scale samples to 16-bit PCM
                            pcm_data = (samples * 32767).astype(np.int16).tobytes()

                            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                            temp_filename = temp_file.name

                            with wave.open(temp_filename, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(self.sample_rate)
                                wf.writeframes(pcm_data)

                            with open(temp_filename, 'rb') as temp_file:
                                options = {
                                    "model": self.whisper_api_model,
                                    "file": temp_file,
                                    "response_format": "verbose_json",
                                    "prompt": self.transcription_options.initial_prompt,
                                }

                                try:
                                    transcript = (
                                        self.openai_client.audio.transcriptions.create(
                                            **options,
                                            language=self.transcription_options.language,
                                        )
                                        if self.transcription_options.task == Task.TRANSCRIBE
                                        else self.openai_client.audio.translations.create(**options)
                                    )

                                    result = {"text": " ".join(
                                        [segment["text"] for segment in transcript.model_extra["segments"]])}
                                except Exception as e:
                                    result = {"text": f"Error: {str(e)}"}

                            os.unlink(temp_filename)

                        next_text: str = result.get("text")

                        # Update initial prompt between successive recording chunks
                        initial_prompt += next_text

                        logging.debug(
                            "Received next result, length = %s, time taken = %s",
                            len(next_text),
                            datetime.datetime.now() - time_started,
                        )
                        self.transcription.emit(next_text)
                    else:
                        self.mutex.release()
        except PortAudioError as exc:
            self.error.emit(str(exc))
            logging.exception("")
            return

        self.finished.emit()

    @staticmethod
    def get_device_sample_rate(device_id: Optional[int]) -> int:
        """Returns the sample rate to be used for recording. It uses the default sample rate
        provided by Whisper if the microphone supports it, or else it uses the device's default
        sample rate.
        """
        sample_rate = whisper_audio.SAMPLE_RATE
        try:
            sounddevice.check_input_settings(device=device_id, samplerate=sample_rate)
            return sample_rate
        except PortAudioError:
            device_info = sounddevice.query_devices(device=device_id)
            if isinstance(device_info, dict):
                return int(device_info.get("default_samplerate", sample_rate))
            return sample_rate

    def stream_callback(self, in_data: np.ndarray, frame_count, time_info, status):
        # Try to enqueue the next block. If the queue is already full, drop the block.
        chunk: np.ndarray = in_data.ravel()
        with self.mutex:
            if self.queue.size < self.max_queue_size:
                self.queue = np.append(self.queue, chunk)

    @staticmethod
    def amplitude(arr: np.ndarray):
        return (abs(max(arr)) + abs(min(arr))) / 2

    def stop_recording(self):
        self.is_running = False
