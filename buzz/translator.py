import logging
import queue

from typing import Optional
from openai import OpenAI
from PyQt6.QtCore import QObject, pyqtSignal

from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.transcriber.transcriber import TranscriptionOptions


class Translator(QObject):
    translation = pyqtSignal(str)
    finished = pyqtSignal()
    is_running = False

    def __init__(
        self,
        transcription_options: TranscriptionOptions,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        logging.debug(f"Translator init: {transcription_options}")

        self.transcription_options = transcription_options
        self.queue = queue.Queue()

        settings = Settings()
        custom_openai_base_url = settings.value(
            key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
        )
        openai_api_key = get_password(Key.OPENAI_API_KEY)
        self.openai_client = OpenAI(
            api_key=openai_api_key,
            base_url=custom_openai_base_url if custom_openai_base_url else None
        )

    def start(self):
        logging.debug("Starting translation queue")

        self.is_running = True

        while self.is_running:
            try:
                transcript = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            completion = self.openai_client.chat.completions.create(
                model=self.transcription_options.llm_model,
                messages=[
                    {"role": "system", "content": self.transcription_options.llm_prompt},
                    {"role": "user", "content": transcript}
                ]
            )

            logging.debug(f"Received translation response: {completion}")

            if completion.choices and completion.choices[0].message:
                next_translation = completion.choices[0].message.content
            else:
                logging.error(f"Translation error! Server response: {completion}")
                next_translation = "Translation error, see logs!"

            self.translation.emit(next_translation)

        self.finished.emit()

    def enqueue(self, transcript: str):
        if self.is_running:
            self.queue.put(transcript)

    def stop(self):
        self.is_running = False
