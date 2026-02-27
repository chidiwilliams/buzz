import time
import pytest
from queue import Empty
from unittest.mock import Mock, patch, create_autospec

from PyQt6.QtCore import QThread

from buzz.translator import Translator
from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog
from buzz.locale import _


class TestParseBatchResponse:
    def test_simple_batch(self):
        response = "[1] Hello\n[2] World"
        result = Translator._parse_batch_response(response, 2)
        assert len(result) == 2
        assert result[0] == "Hello"
        assert result[1] == "World"

    def test_missing_entries_fallback(self):
        response = "[1] Hello\n[3] World"
        result = Translator._parse_batch_response(response, 3)
        assert len(result) == 3
        assert result[0] == "Hello"
        assert result[1] == ""
        assert result[2] == "World"

    def test_multiline_entries(self):
        response = "[1] This is a long\nmultiline translation\n[2] Short"
        result = Translator._parse_batch_response(response, 2)
        assert len(result) == 2
        assert "multiline" in result[0]
        assert result[1] == "Short"

    def test_single_item_batch(self):
        response = "[1] Single translation"
        result = Translator._parse_batch_response(response, 1)
        assert len(result) == 1
        assert result[0] == "Single translation"

    def test_empty_response(self):
        response = ""
        result = Translator._parse_batch_response(response, 2)
        assert len(result) == 2
        assert result[0] == ""
        assert result[1] == ""

    def test_whitespace_handling(self):
        response = "[1]   Hello with spaces   \n[2]   World   "
        result = Translator._parse_batch_response(response, 2)
        assert result[0] == "Hello with spaces"
        assert result[1] == "World"

    def test_out_of_order_entries(self):
        response = "[2] Second\n[1] First"
        result = Translator._parse_batch_response(response, 2)
        assert result[0] == "First"
        assert result[1] == "Second"


class TestTranslator:
    @patch('buzz.translator.OpenAI', autospec=True)
    @patch('buzz.translator.queue.Queue', autospec=True)
    def test_start(self, mock_queue, mock_openai, qtbot):
        def side_effect(*args, **kwargs):
            if side_effect.call_count <= 1:
                side_effect.call_count += 1
                return ("Hello, how are you?", 1)

            # Finally return sentinel to stop
            return None

        side_effect.call_count = 0

        mock_queue.get.side_effect = side_effect
        mock_queue.get_nowait.side_effect = Empty
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

        translator.stop()

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

        time.sleep(1)  # Give thread time to start

        self.translator.enqueue("Hello, how are you?")

        def translation_signal_received():
            assert self.on_next_translation_called

        qtbot.wait_until(translation_signal_received, timeout=60 * 1000)

        if self.translator is not None:
            self.translator.stop()

        if self.translation_thread is not None:
            self.translation_thread.quit()
            # Wait for the thread to actually finish before cleanup
            self.translation_thread.wait()
            # Process pending events to ensure deleteLater() is handled
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.processEvents()
            time.sleep(0.1)  # Give time for cleanup

        # Note: translator and translation_thread will be automatically deleted
        # via the deleteLater() connections set up earlier
