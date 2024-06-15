import time
import pytest
from queue import Empty
from unittest.mock import Mock, patch, create_autospec

from PyQt6.QtCore import QThread

from buzz.translator import Translator
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog


class TestTranslator:
    @patch('buzz.translator.OpenAI', autospec=True)
    @patch('buzz.translator.queue.Queue', autospec=True)
    def test_start(self, mock_queue, mock_openai):
        def side_effect(*args, **kwargs):
            side_effect.call_count += 1

            if side_effect.call_count >= 5:
                translator.is_running = False

            if side_effect.call_count < 3:
                raise Empty
            return "Hello, how are you?", None

        side_effect.call_count = 0

        mock_queue.get.side_effect = side_effect
        mock_chat = Mock()
        mock_openai.return_value.chat = mock_chat
        mock_chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content="AI Translated: Hello, how are you?"))]
        )

        transcription_options = TranscriptionOptions(
            enable_llm_translation=False,
            llm_model="llama3",
            llm_prompt="Please translate this text:",
        )
        translator = Translator(
            transcription_options,
            AdvancedSettingsDialog(
                transcription_options=transcription_options, parent=None
            )
        )
        translator.queue = mock_queue

        translator.start()

        mock_queue.get.assert_called()
        mock_chat.completions.create.assert_called()

    @patch('buzz.translator.OpenAI', autospec=True)
    def test_translator(self, mock_openai, qtbot):

        self.on_next_translation_called = False

        def on_next_translation(text: str):
            self.on_next_translation_called = True
            assert text.startswith("AI Translated:")

        mock_chat = Mock()
        mock_openai.return_value.chat = mock_chat
        mock_chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content="AI Translated: Hello, how are you?"))]
        )

        self.translation_thread = QThread()
        self.transcription_options = TranscriptionOptions(
            enable_llm_translation=False,
            llm_model="llama3",
            llm_prompt="Please translate this text:",
        )

        self.translator = Translator(
            self.transcription_options,
            AdvancedSettingsDialog(
                transcription_options=self.transcription_options, parent=None
            )
        )

        self.translator.moveToThread(self.translation_thread)

        self.translation_thread.started.connect(self.translator.start)
        self.translation_thread.finished.connect(
            self.translation_thread.deleteLater
        )

        self.translator.finished.connect(self.translation_thread.quit)
        self.translator.finished.connect(self.translator.deleteLater)

        self.translator.translation.connect(on_next_translation)

        self.translation_thread.start()

        time.sleep(3)
        assert self.translator.is_running

        self.translator.enqueue("Hello, how are you?")

        def translation_signal_received():
            assert self.on_next_translation_called

        qtbot.wait_until(translation_signal_received, timeout=60 * 1000)

        if self.translator is not None:
            self.translator.stop()
            self.translator.deleteLater()

        if self.translation_thread is not None:
            self.translation_thread.quit()
            self.translation_thread.deleteLater()

        # Wait to clean-up threads
        time.sleep(3)
