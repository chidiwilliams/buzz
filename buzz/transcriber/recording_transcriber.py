import datetime
import logging
import platform
import os
import sys
import wave
import time
import tempfile
import threading
import subprocess
from typing import Optional
from platformdirs import user_cache_dir

import torch
import numpy as np
import sounddevice
from sounddevice import PortAudioError
from openai import OpenAI
from PyQt6.QtCore import QObject, pyqtSignal

from buzz import whisper_audio
from buzz.locale import _
from buzz.assets import APP_BASE_DIR
from buzz.model_loader import ModelType, get_custom_api_whisper_model
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import TranscriptionOptions, Task
from buzz.transcriber.whisper_cpp import WhisperCpp
from buzz.transformers_whisper import TransformersWhisper
from buzz.settings.recording_transcriber_mode import RecordingTranscriberMode

import whisper
import faster_whisper


class RecordingTranscriber(QObject):
    transcription = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    is_running = False
    SAMPLE_RATE = whisper_audio.SAMPLE_RATE

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
        self.settings = Settings()
        self.transcriber_mode = list(RecordingTranscriberMode)[
            self.settings.value(key=Settings.Key.RECORDING_TRANSCRIBER_MODE, default_value=0)]
        self.transcription_options = transcription_options
        self.current_stream = None
        self.input_device_index = input_device_index
        self.sample_rate = sample_rate if sample_rate is not None else whisper_audio.SAMPLE_RATE
        self.model_path = model_path
        self.n_batch_samples = 5 * self.sample_rate  # 5 seconds
        self.keep_sample_seconds = 0.15
        if self.transcriber_mode == RecordingTranscriberMode.APPEND_AND_CORRECT:
            self.n_batch_samples = 3 * self.sample_rate  # 3 seconds
            self.keep_sample_seconds = 1.5
        # pause queueing if more than 3 batches behind
        self.max_queue_size = 3 * self.n_batch_samples
        self.queue = np.ndarray([], dtype=np.float32)
        self.mutex = threading.Lock()
        self.sounddevice = sounddevice
        self.openai_client = None
        self.whisper_api_model = get_custom_api_whisper_model("")
        self.is_windows = sys.platform == "win32"
        self.process = None

    def start(self):
        model = None
        model_path = self.model_path
        keep_samples = int(self.keep_sample_seconds * self.sample_rate)

        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        use_cuda = torch.cuda.is_available() and force_cpu == "false"

        if torch.cuda.is_available():
            logging.debug(f"CUDA version detected: {torch.version.cuda}")

        if self.transcription_options.model.model_type == ModelType.WHISPER:
            device = "cuda" if use_cuda else "cpu"
            model = whisper.load_model(model_path, device=device)
        elif self.transcription_options.model.model_type == ModelType.WHISPER_CPP:
            # As DLL mode on Windows is somewhat unreliable, will use local whisper-server
            if self.is_windows:
                self.start_local_whisper_server()
            else:
                model = WhisperCpp(model_path)
        elif self.transcription_options.model.model_type == ModelType.FASTER_WHISPER:
            model_root_dir = user_cache_dir("Buzz")
            model_root_dir = os.path.join(model_root_dir, "models")
            model_root_dir = os.getenv("BUZZ_MODEL_ROOT", model_root_dir)

            device = "auto"
            if torch.cuda.is_available() and torch.version.cuda < "12":
                logging.debug("Unsupported CUDA version (<12), using CPU")
                device = "cpu"

            if not torch.cuda.is_available():
                logging.debug("CUDA is not available, using CPU")
                device = "cpu"

            if force_cpu != "false":
                device = "cpu"

            model = faster_whisper.WhisperModel(
                model_size_or_path=model_path,
                download_root=model_root_dir,
                device=device,
                cpu_threads=(os.cpu_count() or 8)//2,
            )

            # This was commented out as it was causing issues. On the other hand some users are reporting errors without
            # this. It is possible issues were present in older model versions without some config files and now are fixed
            #
            # Fix for large-v3 https://github.com/guillaumekln/faster-whisper/issues/547#issuecomment-1797962599
            # if self.transcription_options.model.whisper_model_size in {WhisperModelSize.LARGEV3, WhisperModelSize.LARGEV3TURBO}:
            #     model.feature_extractor.mel_filters = model.feature_extractor.get_mel_filters(
            #         model.feature_extractor.sampling_rate, model.feature_extractor.n_fft, n_mels=128
            #     )
        elif self.transcription_options.model.model_type == ModelType.OPEN_AI_WHISPER_API:
            custom_openai_base_url = self.settings.value(
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
                    if self.queue.size >= self.n_batch_samples:
                        self.mutex.acquire()
                        samples = self.queue[: self.n_batch_samples]
                        self.queue = self.queue[self.n_batch_samples - keep_samples:]
                        self.mutex.release()

                        amplitude = self.amplitude(samples)

                        logging.debug(
                            "Processing next frame, sample size = %s, queue size = %s, amplitude = %s",
                            samples.size,
                            self.queue.size,
                            amplitude,
                        )

                        if amplitude < 0.025:
                            time.sleep(0.5)
                            continue

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
                                no_speech_threshold=0.4
                            )
                        elif (
                                self.transcription_options.model.model_type
                                == ModelType.WHISPER_CPP
                                # On Windows we use the local whisper server via OpenAI API
                                and not self.is_windows
                        ):
                            assert isinstance(model, WhisperCpp)
                            result = model.transcribe(
                                audio=samples,
                                params=model.get_params(
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
                                word_timestamps=False,
                                without_timestamps=True,
                                no_speech_threshold=0.4,
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
                            if self.openai_client is None:
                                self.transcription.emit(_("A connection error occurred"))
                                self.stop_recording()
                                return

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
                                    "response_format": "json",
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

                                    if "segments" in transcript.model_extra:
                                        result = {"text": " ".join(
                                            [segment["text"] for segment in transcript.model_extra["segments"]])}
                                    else:
                                        result = {"text": transcript.text}

                                except Exception as e:
                                    if self.is_running:
                                        result = {"text": f"Error: {str(e)}"}
                                    else:
                                        result = {"text": ""}

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
                        time.sleep(0.5)

        except PortAudioError as exc:
            self.error.emit(str(exc))
            logging.exception("")
            return

        self.finished.emit()

        # Cleanup
        if model:
            del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

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
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()

    def start_local_whisper_server(self):
        self.transcription.emit(_("Starting Whisper.cpp..."))

        self.process = None
        command = [
            os.path.join(APP_BASE_DIR, "whisper-server.exe"),
            "--port", "3004",
            "--inference-path", "/audio/transcriptions",
            "--threads", str(os.getenv("BUZZ_WHISPERCPP_N_THREADS", (os.cpu_count() or 8) // 2)),
            "--model", self.model_path,
            "--no-timestamps",
            "--no-context",  # on Windows context causes duplications of last message
        ]

        if self.transcription_options.language is not None:
            command.extend(["--language", self.transcription_options.language])

        logging.debug(f"Starting Whisper server with command: {' '.join(command)}")

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,  # For debug set to subprocess.PIPE, but it will freeze on Windows after ~30 seconds
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        # Wait for server to start and load model
        time.sleep(10)

        if self.process is not None and self.process.poll() is None:
            logging.debug(f"Whisper server started successfully.")
            logging.debug(f"Model: {self.model_path}")
        else:
            stderr_output = self.process.stderr.read().decode()
            logging.error(f"Whisper server failed to start. Error: {stderr_output}")

            self.transcription.emit(_("Whisper server failed to start. Check logs for details."))

            if "ErrorOutOfDeviceMemory" in stderr_output:
                message = _("Whisper server failed to start due to insufficient memory. "
                            "Please try again with a smaller model. "
                            "To force CPU mode use BUZZ_FORCE_CPU=TRUE environment variable.")
                logging.error(message)
                self.transcription.emit(message)

            self.transcription.emit(_("Whisper server failed to start. Check logs for details."))
            return

        self.openai_client = OpenAI(
            api_key="not-used",
            base_url="http://127.0.0.1:3004",
            timeout=10.0,
            max_retries=0
        )

    def __del__(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()