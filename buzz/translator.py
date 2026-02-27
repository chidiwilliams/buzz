import os
import re
import logging
import queue

from typing import Optional, List, Tuple
from openai import OpenAI, max_retries
from PyQt6.QtCore import QObject, pyqtSignal

from buzz.locale import _
from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog


BATCH_SIZE = 10


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

    def _translate_single(self, transcript: str, transcript_id: int) -> Tuple[str, int]:
        """Translate a single transcript via the API. Returns (translation, transcript_id)."""
        try:
            completion = self.openai_client.chat.completions.create(
                model=self.transcription_options.llm_model,
                messages=[
                    {"role": "system", "content": self.transcription_options.llm_prompt},
                    {"role": "user", "content": transcript}
                ],
                timeout=60.0,
            )
        except Exception as e:
            completion = None
            logging.error(f"Translation error! Server response: {e}")

        if completion and completion.choices and completion.choices[0].message:
            logging.debug(f"Received translation response: {completion}")
            return completion.choices[0].message.content, transcript_id
        else:
            logging.error(f"Translation error! Server response: {completion}")
            # Translation error
            return "", transcript_id

    def _translate_batch(self, items: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
        """Translate multiple transcripts in a single API call.
        Returns list of (translation, transcript_id) in the same order as input."""
        numbered_parts = []
        for i, (transcript, _) in enumerate(items, 1):
            numbered_parts.append(f"[{i}] {transcript}")
        combined = "\n".join(numbered_parts)

        batch_prompt = (
            f"{self.transcription_options.llm_prompt}\n\n"
            f"You will receive {len(items)} numbered texts. "
            f"Process each one separately according to the instruction above "
            f"and return them in the exact same numbered format, e.g.:\n"
            f"[1] processed text\n[2] processed text"
        )

        try:
            completion = self.openai_client.chat.completions.create(
                model=self.transcription_options.llm_model,
                messages=[
                    {"role": "system", "content": batch_prompt},
                    {"role": "user", "content": combined}
                ],
                timeout=60.0,
            )
        except Exception as e:
            completion = None
            logging.error(f"Batch translation error! Server response: {e}")

        if not (completion and completion.choices and completion.choices[0].message):
            logging.error(f"Batch translation error! Server response: {completion}")
            # Translation error
            return [("", tid) for _, tid in items]

        response_text = completion.choices[0].message.content
        logging.debug(f"Received batch translation response: {response_text}")

        translations = self._parse_batch_response(response_text, len(items))

        results = []
        for i, (_, transcript_id) in enumerate(items):
            if i < len(translations):
                results.append((translations[i], transcript_id))
            else:
                # Translation error
                results.append(("", transcript_id))
        return results

    @staticmethod
    def _parse_batch_response(response: str, expected_count: int) -> List[str]:
        """Parse a numbered batch response like '[1] text\\n[2] text' into a list of strings."""
        # Split on [N] markers — re.split with a group returns: [before, group1, after1, group2, after2, ...]
        parts = re.split(r'\[(\d+)\]\s*', response)

        translations = {}
        for i in range(1, len(parts) - 1, 2):
            num = int(parts[i])
            text = parts[i + 1].strip()
            translations[num] = text

        return [
            translations.get(i, "")
            for i in range(1, expected_count + 1)
        ]

    def start(self):
        logging.debug("Starting translation queue")

        while True:
            item = self.queue.get()  # Block until item available

            # Check for sentinel value (None means stop)
            if item is None:
                logging.debug("Translation queue received stop signal")
                break

            # Collect a batch: start with the first item, then drain more
            batch = [item]
            stop_after_batch = False
            while len(batch) < BATCH_SIZE:
                try:
                    next_item = self.queue.get_nowait()
                    if next_item is None:
                        stop_after_batch = True
                        break
                    batch.append(next_item)
                except queue.Empty:
                    break

            if len(batch) == 1:
                transcript, transcript_id = batch[0]
                translation, tid = self._translate_single(transcript, transcript_id)
                self.translation.emit(translation, tid)
            else:
                logging.debug(f"Translating batch of {len(batch)} in single request")
                results = self._translate_batch(batch)
                for translation, tid in results:
                    self.translation.emit(translation, tid)

            if stop_after_batch:
                logging.debug("Translation queue received stop signal")
                break

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
