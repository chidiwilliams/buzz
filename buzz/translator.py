import os
import logging
import queue

from typing import Optional
from openai import OpenAI, max_retries
from PyQt6.QtCore import QObject, pyqtSignal

from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog


class Translator(QObject):
    translation = pyqtSignal(str, int)
    finished = pyqtSignal()

    def __init__(
        self,
        transcription_options: TranscriptionOptions,
        advanced_settings_dialog: AdvancedSettingsDialog,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        logging.debug(f"Translator init: {transcription_options}")

        self.transcription_options = transcription_options
        self.advanced_settings_dialog = advanced_settings_dialog
        self.advanced_settings_dialog.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        self.queue = queue.Queue()

        settings = Settings()
        custom_openai_base_url = os.getenv(
            "BUZZ_TRANSLATION_API_BASE_URl",
            settings.value(
                key=Settings.Key.CUSTOM_OPENAI_BASE_URL, default_value=""
            )
        )
        openai_api_key = os.getenv(
            "BUZZ_TRANSLATION_API_KEY",
            get_password(Key.OPENAI_API_KEY)
        )
        self.openai_client = OpenAI(
            api_key=openai_api_key,
            base_url=custom_openai_base_url if custom_openai_base_url else None,
            max_retries=0
        )

    def start(self):
        logging.debug("Starting translation queue")

        while True:
            item = self.queue.get()  # Block until item available

            # Check for sentinel value (None means stop)
            if item is None:
                logging.debug("Translation queue received stop signal")
                break

            transcript, transcript_id = item

            try:
                completion = self.openai_client.chat.completions.create(
                    model=self.transcription_options.llm_model,
                    messages=[
                        {"role": "system", "content": self.transcription_options.llm_prompt},
                        {"role": "user", "content": transcript}
                    ],
                    timeout=30.0,

                )
            except Exception as e:
                completion = None
                logging.error(f"Translation error! Server response: {e}")

            if completion and completion.choices and completion.choices[0].message:
                logging.debug(f"Received translation response: {completion}")
                next_translation = completion.choices[0].message.content
            else:
                logging.error(f"Translation error! Server response: {completion}")
                next_translation = "Translation error, see logs!"

            self.translation.emit(next_translation, transcript_id)

        logging.debug("Translation queue stopped")
        self.finished.emit()

    def on_transcription_options_changed(
        self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options

    def enqueue(self, transcript: str, transcript_id: Optional[int] = None):
        self.queue.put((transcript, transcript_id))

    def stop(self):
        # Send sentinel value to unblock and stop the worker thread
        self.queue.put(None)
