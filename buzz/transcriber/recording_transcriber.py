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

# Preload CUDA libraries before importing torch
from buzz import cuda_setup  # noqa: F401

import torch
import numpy as np
import sounddevice
from sounddevice import PortAudioError
from openai import OpenAI
from PyQt6.QtCore import QObject, pyqtSignal

from buzz import whisper_audio
from buzz.locale import _
from buzz.assets import APP_BASE_DIR
from buzz.model_loader import ModelType, map_language_to_mms
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import TranscriptionOptions, Task
from buzz.transformers_whisper import TransformersTranscriber
from buzz.settings.recording_transcriber_mode import RecordingTranscriberMode

import whisper
import faster_whisper


class RecordingTranscriber(QObject):
    transcription = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    amplitude_changed = pyqtSignal(float)
    average_amplitude_changed = pyqtSignal(float)
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
        self.whisper_api_model = self.settings.value(
            key=Settings.Key.OPENAI_API_MODEL, default_value="whisper-1"
        )
        self.process = None
        self._stderr_lines: list[bytes] = []

    def start(self):
        self.is_running = True
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
            self.start_local_whisper_server()
            if self.openai_client is None:
                if not self.is_running:
                    self.finished.emit()
                else:
                    self.error.emit(_("Whisper server failed to start. Check logs for details."))
                return
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

            # Check if user wants reduced GPU memory usage (int8 quantization)
            reduce_gpu_memory = os.getenv("BUZZ_REDUCE_GPU_MEMORY", "false") != "false"
            compute_type = "default"
            if reduce_gpu_memory:
                compute_type = "int8" if device == "cpu" else "int8_float16"
                logging.debug(f"Using {compute_type} compute type for reduced memory usage")

            model = faster_whisper.WhisperModel(
                model_size_or_path=model_path,
                download_root=model_root_dir,
                device=device,
                compute_type=compute_type,
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
            self.openai_client = OpenAI(
                api_key=self.transcription_options.openai_access_token,
                base_url=custom_openai_base_url if custom_openai_base_url else None,
                max_retries=0
            )
            logging.debug("Will use whisper API on %s, %s",
                          custom_openai_base_url, self.whisper_api_model)
        else:  # ModelType.HUGGING_FACE
            model = TransformersTranscriber(model_path)

        initial_prompt = self.transcription_options.initial_prompt

        logging.debug(
            "Recording, transcription options = %s, model path = %s, sample rate = %s, device = %s",
            self.transcription_options,
            model_path,
            self.sample_rate,
            self.input_device_index,
        )

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
                        self.average_amplitude_changed.emit(amplitude)

                        logging.debug(
                            "Processing next frame, sample size = %s, queue size = %s, amplitude = %s",
                            samples.size,
                            self.queue.size,
                            amplitude,
                        )

                        if amplitude < self.transcription_options.silence_threshold:
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
                                no_speech_threshold=0.4,
                                fp16=False,
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
                                # Prevent crash on Windows https://github.com/SYSTRAN/faster-whisper/issues/71#issuecomment-1526263764
                                temperature=0 if platform.system() == "Windows" else self.transcription_options.temperature,
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
                            assert isinstance(model, TransformersTranscriber)
                            # Handle MMS-specific language and task
                            if model.is_mms_model:
                                language = map_language_to_mms(
                                    self.transcription_options.language or "eng"
                                )
                                effective_task = Task.TRANSCRIBE.value
                            else:
                                language = (
                                    self.transcription_options.language
                                    if self.transcription_options.language is not None
                                    else "en"
                                )
                                effective_task = self.transcription_options.task.value

                            result = model.transcribe(
                                audio=samples,
                                language=language,
                                task=effective_task,
                            )
                        else:  # OPEN_AI_WHISPER_API, also used for WHISPER_CPP
                            if self.openai_client is None:
                                self.error.emit(_("A connection error occurred"))
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
                        initial_prompt = next_text

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
            logging.exception("PortAudio error during recording")
            return
        except Exception as exc:
            logging.exception("Unexpected error during recording")
            self.error.emit(str(exc))
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

        amplitude = self.amplitude(chunk)
        self.amplitude_changed.emit(amplitude)

        with self.mutex:
            if self.queue.size < self.max_queue_size:
                self.queue = np.append(self.queue, chunk)

    @staticmethod
    def amplitude(arr: np.ndarray):
        return float(np.sqrt(np.mean(arr**2)))

    def _drain_stderr(self):
        if self.process and self.process.stderr:
            for line in self.process.stderr:
                self._stderr_lines.append(line)

    def stop_recording(self):
        self.is_running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                logging.warning("Whisper server process had to be killed after timeout")

    def start_local_whisper_server(self):
        # Reduce verbose HTTP client logging from OpenAI/httpx
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)

        self.transcription.emit(_("Starting Whisper.cpp..."))

        if platform.system() == "Darwin" and platform.machine() == "arm64":
            self.transcription.emit(_("First time use of a model may take up to several minutest to load."))

        self.process = None

        server_executable = "whisper-server.exe" if sys.platform == "win32" else "whisper-server"
        server_path = os.path.join(APP_BASE_DIR, "whisper_cpp", server_executable)

        # If running Mac and Windows installed version
        if not os.path.exists(server_path):
            server_path = os.path.join(APP_BASE_DIR, "buzz", "whisper_cpp", server_executable)

        cmd = [
            server_path,
            "--port", "3003",
            "--inference-path", "/audio/transcriptions",
            "--threads", str(os.getenv("BUZZ_WHISPERCPP_N_THREADS", (os.cpu_count() or 8) // 2)),
            "--model", self.model_path,
            "--no-timestamps",
            # Protections against hallucinated repetition. Seems to be problem on macOS
            # https://github.com/ggml-org/whisper.cpp/issues/1507
            "--max-context", "64",
            "--entropy-thold", "2.8",
            "--suppress-nst"
        ]

        if self.transcription_options.language is not None:
            cmd.extend(["--language", self.transcription_options.language])
        else:
            cmd.extend(["--language", "auto"])

        logging.debug(f"Starting Whisper server with command: {' '.join(cmd)}")

        try:
            if sys.platform == "win32":
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    shell=False,
                )
        except Exception as e:
            error_msg = f"Failed to start whisper-server subprocess: {str(e)}"
            logging.error(error_msg)
            return

        # Drain stderr in a background thread to prevent pipe buffer from filling
        # up and blocking the subprocess (especially on Windows with compiled exe).
        self._stderr_lines = []
        stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        stderr_thread.start()

        # Wait for server to start and load model, checking periodically
        for i in range(100):  # 10 seconds total, in 0.1s increments
            if not self.is_running or self.process.poll() is not None:
                break
            time.sleep(0.1)

        if self.process is not None and self.process.poll() is None:
            self.transcription.emit(_("Starting transcription..."))
            logging.debug(f"Whisper server started successfully.")
            logging.debug(f"Model: {self.model_path}")
        else:
            stderr_thread.join(timeout=2)
            stderr_output = b"".join(self._stderr_lines).decode(errors="replace")
            logging.error(f"Whisper server failed to start. Error: {stderr_output}")

            self.transcription.emit(_("Whisper server failed to start. Check logs for details."))

            if "ErrorOutOfDeviceMemory" in stderr_output:
                message = _(
                    "Whisper server failed to start due to insufficient memory. "
                    "Please try again with a smaller model. "
                    "To force CPU mode use BUZZ_FORCE_CPU=TRUE environment variable."
                )
                logging.error(message)
                self.transcription.emit(message)

            return

        self.openai_client = OpenAI(
            api_key="not-used",
            base_url="http://127.0.0.1:3003",
            timeout=30.0,
            max_retries=0
        )

    def __del__(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()