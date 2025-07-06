import logging
import os
import time
import subprocess
from typing import Optional, List

from PyQt6.QtCore import QObject
from openai import OpenAI

from buzz.locale import _
from buzz.assets import APP_BASE_DIR
from buzz.transcriber.openai_whisper_api_file_transcriber import OpenAIWhisperAPIFileTranscriber
from buzz.transcriber.transcriber import FileTranscriptionTask, Segment


class LocalWhisperCppServerTranscriber(OpenAIWhisperAPIFileTranscriber):
    # To be used on Windows only
    def __init__(self, task: FileTranscriptionTask, parent: Optional["QObject"] = None) -> None:
        super().__init__(task=task, parent=parent)

        self.process = None
        self.initialization_error = None
        command = [
            os.path.join(APP_BASE_DIR, "whisper-server.exe"),
            "--port", "3000",
            "--inference-path", "/audio/transcriptions",
            "--threads", str(os.getenv("BUZZ_WHISPERCPP_N_THREADS", (os.cpu_count() or 8)//2)),
            "--language", task.transcription_options.language,
            "--model", task.model_path
        ]

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        # Wait for server to start and load model
        time.sleep(10)

        if self.process is not None and self.process.poll() is None:
            logging.debug(f"Whisper server started successfully.")
            logging.debug(f"Model: {task.model_path}")
        else:
            stderr_output = self.process.stderr.read().decode()
            logging.error(f"Whisper server failed to start. Error: {stderr_output}")
            self.initialization_error = _("Whisper server failed to start. Check logs for details.")

            if "ErrorOutOfDeviceMemory" in stderr_output:
                self.initialization_error = _("Whisper server failed to start due to insufficient memory. "
                                              "Please try again with a smaller model. "
                                              "To force CPU mode use BUZZ_FORCE_CPU=TRUE environment variable.")

        self.openai_client = OpenAI(
            api_key="not-used",
            base_url="http://127.0.0.1:3000"
        )

    def transcribe(self) -> List[Segment]:
        if self.initialization_error:
            raise Exception(self.initialization_error)

        return super().transcribe()


    def __del__(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait()
