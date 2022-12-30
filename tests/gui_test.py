import logging
import os.path
import pathlib
import platform
from unittest.mock import Mock, patch

import pytest
import sounddevice
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QValidator, QKeyEvent
from PyQt6.QtWidgets import QPushButton, QToolBar, QTableWidget, QApplication
from pytestqt.qtbot import QtBot

from buzz.cache import TasksCache
from buzz.gui import (AboutDialog, AdvancedSettingsDialog, Application,
                      AudioDevicesComboBox, DownloadModelProgressDialog,
                      FileTranscriberWidget, LanguagesComboBox, MainWindow,
                      RecordingTranscriberWidget,
                      TemperatureValidator, TextDisplayBox,
                      TranscriptionTasksTableWidget, TranscriptionViewerWidget, HuggingFaceSearchLineEdit,
                      TranscriptionOptionsGroupBox)
from buzz.model_loader import ModelType
from buzz.transcriber import (FileTranscriptionOptions, FileTranscriptionTask,
                              Segment, TranscriptionOptions)
from tests.mock_sounddevice import MockInputStream


class TestApplication:
    # FIXME: this seems to break the tests if not run??
    app = Application()

    def test_should_open_application(self):
        assert self.app is not None


class TestLanguagesComboBox:
    languagesComboxBox = LanguagesComboBox('en')

    def test_should_show_sorted_whisper_languages(self):
        assert self.languagesComboxBox.itemText(0) == 'Detect Language'
        assert self.languagesComboxBox.itemText(10) == 'Belarusian'
        assert self.languagesComboxBox.itemText(20) == 'Dutch'
        assert self.languagesComboxBox.itemText(30) == 'Gujarati'
        assert self.languagesComboxBox.itemText(40) == 'Japanese'
        assert self.languagesComboxBox.itemText(50) == 'Lithuanian'

    def test_should_select_en_as_default_language(self):
        assert self.languagesComboxBox.currentText() == 'English'

    def test_should_select_detect_language_as_default(self):
        languages_combo_box = LanguagesComboBox(None)
        assert languages_combo_box.currentText() == 'Detect Language'


class TestAudioDevicesComboBox:
    mock_query_devices = [
        {'name': 'Background Music', 'index': 0, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2,
         'default_low_input_latency': 0.01,
         'default_low_output_latency': 0.008, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.064,
         'default_samplerate': 8000.0},
        {'name': 'Background Music (UI Sounds)', 'index': 1, 'hostapi': 0, 'max_input_channels': 2,
         'max_output_channels': 2, 'default_low_input_latency': 0.01,
         'default_low_output_latency': 0.008, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.064,
         'default_samplerate': 8000.0},
        {'name': 'BlackHole 2ch', 'index': 2, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2,
         'default_low_input_latency': 0.01,
         'default_low_output_latency': 0.0013333333333333333, 'default_high_input_latency': 0.1,
         'default_high_output_latency': 0.010666666666666666, 'default_samplerate': 48000.0},
        {'name': 'MacBook Pro Microphone', 'index': 3, 'hostapi': 0, 'max_input_channels': 1, 'max_output_channels': 0,
         'default_low_input_latency': 0.034520833333333334,
         'default_low_output_latency': 0.01, 'default_high_input_latency': 0.043854166666666666,
         'default_high_output_latency': 0.1, 'default_samplerate': 48000.0},
        {'name': 'MacBook Pro Speakers', 'index': 4, 'hostapi': 0, 'max_input_channels': 0, 'max_output_channels': 2,
         'default_low_input_latency': 0.01,
         'default_low_output_latency': 0.0070416666666666666, 'default_high_input_latency': 0.1,
         'default_high_output_latency': 0.016375, 'default_samplerate': 48000.0},
        {'name': 'Null Audio Device', 'index': 5, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2,
         'default_low_input_latency': 0.01,
         'default_low_output_latency': 0.0014512471655328798, 'default_high_input_latency': 0.1,
         'default_high_output_latency': 0.011609977324263039, 'default_samplerate': 44100.0},
        {'name': 'Multi-Output Device', 'index': 6, 'hostapi': 0, 'max_input_channels': 0, 'max_output_channels': 2,
         'default_low_input_latency': 0.01,
         'default_low_output_latency': 0.0033333333333333335, 'default_high_input_latency': 0.1,
         'default_high_output_latency': 0.012666666666666666, 'default_samplerate': 48000.0},
    ]

    def test_get_devices(self):
        with patch('sounddevice.query_devices') as query_devices_mock:
            query_devices_mock.return_value = self.mock_query_devices

            sounddevice.default.device = 3, 4

            audio_devices_combo_box = AudioDevicesComboBox()

            assert audio_devices_combo_box.itemText(0) == 'Background Music'
            assert audio_devices_combo_box.itemText(
                1) == 'Background Music (UI Sounds)'
            assert audio_devices_combo_box.itemText(2) == 'BlackHole 2ch'
            assert audio_devices_combo_box.itemText(
                3) == 'MacBook Pro Microphone'
            assert audio_devices_combo_box.itemText(4) == 'Null Audio Device'

            assert audio_devices_combo_box.currentText() == 'MacBook Pro Microphone'

    def test_select_default_mic_when_no_default(self):
        with patch('sounddevice.query_devices') as query_devices_mock:
            query_devices_mock.return_value = self.mock_query_devices

            sounddevice.default.device = -1, 1

            audio_devices_combo_box = AudioDevicesComboBox()

            assert audio_devices_combo_box.currentText() == 'Background Music'


class TestDownloadModelProgressDialog:
    def test_should_show_dialog(self, qtbot: QtBot):
        dialog = DownloadModelProgressDialog(parent=None)
        qtbot.add_widget(dialog)
        assert dialog.labelText() == 'Downloading model (0%, unknown time remaining)'

    def test_should_update_label_on_progress(self, qtbot: QtBot):
        dialog = DownloadModelProgressDialog(parent=None)
        qtbot.add_widget(dialog)
        dialog.set_fraction_completed(0.0)

        dialog.set_fraction_completed(0.01)
        logging.debug(dialog.labelText())
        assert dialog.labelText().startswith(
            'Downloading model (1%')

        dialog.set_fraction_completed(0.1)
        assert dialog.labelText().startswith(
            'Downloading model (10%')

    # Other windows should not be processing while models are being downloaded
    def test_should_be_an_application_modal(self, qtbot: QtBot):
        dialog = DownloadModelProgressDialog(parent=None)
        qtbot.add_widget(dialog)
        assert dialog.windowModality() == Qt.WindowModality.ApplicationModal


@pytest.fixture
def tasks_cache(tmp_path):
    cache = TasksCache(cache_dir=str(tmp_path))
    yield cache
    cache.clear()


def get_test_asset(filename: str):
    return os.path.join(os.path.dirname(__file__), '../testdata/', filename)


class TestMainWindow:

    def test_should_set_window_title_and_icon(self, qtbot):
        window = MainWindow()
        qtbot.add_widget(window)
        assert window.windowTitle() == 'Buzz'
        assert window.windowIcon().pixmap(QSize(64, 64)).isNull() is False
        window.close()

    def test_should_run_transcription_task(self, qtbot: QtBot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        toolbar: QToolBar = window.findChild(QToolBar)
        new_transcription_action = [action for action in toolbar.actions() if action.text() == 'New Transcription'][0]

        with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileNames') as open_file_names_mock:
            open_file_names_mock.return_value = ([get_test_asset('whisper-french.mp3')], '')
            new_transcription_action.trigger()

        file_transcriber_widget: FileTranscriberWidget = window.findChild(FileTranscriberWidget)
        run_button: QPushButton = file_transcriber_widget.findChild(QPushButton)
        run_button.click()

        def check_task_completed():
            table_widget: QTableWidget = window.findChild(QTableWidget)
            assert table_widget.rowCount() == 1
            assert table_widget.item(0, 1).text() == 'whisper-french.mp3'
            assert table_widget.item(0, 2).text() == 'Completed'

        qtbot.wait_until(check_task_completed, timeout=60 * 1000)


class TestFileTranscriberWidget:
    widget = FileTranscriberWidget(
        file_paths=['testdata/whisper-french.mp3'], parent=None)

    def test_should_set_window_title(self, qtbot: QtBot):
        qtbot.addWidget(self.widget)
        assert self.widget.windowTitle() == 'whisper-french.mp3'

    def test_should_emit_triggered_event(self, qtbot: QtBot):
        widget = FileTranscriberWidget(
            file_paths=['testdata/whisper-french.mp3'], parent=None)
        qtbot.addWidget(widget)

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)

        with qtbot.wait_signal(widget.triggered, timeout=30 * 1000):
            qtbot.mouseClick(widget.run_button, Qt.MouseButton.LeftButton)

        transcription_options, file_transcription_options, model_path = mock_triggered.call_args[
            0][0]
        assert transcription_options.language is None
        assert file_transcription_options.file_paths == [
            'testdata/whisper-french.mp3']
        assert len(model_path) > 0


class TestAboutDialog:
    def test_should_create(self):
        dialog = AboutDialog()
        assert dialog is not None


class TestAdvancedSettingsDialog:
    def test_should_update_advanced_settings(self, qtbot: QtBot):
        dialog = AdvancedSettingsDialog(
            transcription_options=TranscriptionOptions(temperature=(0.0, 0.8), initial_prompt='prompt'))
        qtbot.add_widget(dialog)

        transcription_options_mock = Mock()
        dialog.transcription_options_changed.connect(
            transcription_options_mock)

        assert dialog.windowTitle() == 'Advanced Settings'
        assert dialog.temperature_line_edit.text() == '0.0, 0.8'
        assert dialog.initial_prompt_text_edit.toPlainText() == 'prompt'

        dialog.temperature_line_edit.setText('0.0, 0.8, 1.0')
        dialog.initial_prompt_text_edit.setPlainText('new prompt')

        assert transcription_options_mock.call_args[0][0].temperature == (
            0.0, 0.8, 1.0)
        assert transcription_options_mock.call_args[0][0].initial_prompt == 'new prompt'


class TestTemperatureValidator:
    validator = TemperatureValidator(None)

    @pytest.mark.parametrize(
        'text,state',
        [
            ('0.0,0.5,1.0', QValidator.State.Acceptable),
            ('0.0,0.5,', QValidator.State.Intermediate),
            ('0.0,0.5,p', QValidator.State.Invalid),
        ])
    def test_should_validate_temperature(self, text: str, state: QValidator.State):
        assert self.validator.validate(text, 0)[0] == state


class TestTranscriptionViewerWidget:
    widget = TranscriptionViewerWidget(
        transcription_task=FileTranscriptionTask(
            id=0,
            file_path='testdata/whisper-french.mp3',
            file_transcription_options=FileTranscriptionOptions(
                file_paths=['testdata/whisper-french.mp3']),
            transcription_options=TranscriptionOptions(),
            segments=[Segment(40, 299, 'Bien'),
                      Segment(299, 329, 'venue dans')],
            model_path=''))

    def test_should_display_segments(self, qtbot: QtBot):
        qtbot.add_widget(self.widget)

        assert self.widget.windowTitle() == 'whisper-french.mp3'

        text_display_box = self.widget.findChild(TextDisplayBox)
        assert isinstance(text_display_box, TextDisplayBox)
        assert text_display_box.toPlainText(
        ) == '00:00:00.040 --> 00:00:00.299\nBien\n\n00:00:00.299 --> 00:00:00.329\nvenue dans'

    def test_should_export_segments(self, tmp_path: pathlib.Path, qtbot: QtBot):
        qtbot.add_widget(self.widget)

        export_button = self.widget.findChild(QPushButton)
        assert isinstance(export_button, QPushButton)

        output_file_path = tmp_path / 'whisper.txt'
        with patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName') as save_file_name_mock:
            save_file_name_mock.return_value = (str(output_file_path), '')
            export_button.menu().actions()[0].trigger()

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert 'Bien venue dans' in output_file.read()


class TestTranscriptionTasksTableWidget:
    widget = TranscriptionTasksTableWidget()

    def test_upsert_task(self, qtbot: QtBot):
        qtbot.add_widget(self.widget)

        task = FileTranscriptionTask(id=0, file_path='testdata/whisper-french.mp3',
                                     transcription_options=TranscriptionOptions(),
                                     file_transcription_options=FileTranscriptionOptions(
                                         file_paths=['testdata/whisper-french.mp3']), model_path='',
                                     status=FileTranscriptionTask.Status.QUEUED)

        self.widget.upsert_task(task)

        assert self.widget.rowCount() == 1
        assert self.widget.item(0, 1).text() == 'whisper-french.mp3'
        assert self.widget.item(0, 2).text() == 'Queued'

        task.status = FileTranscriptionTask.Status.IN_PROGRESS
        task.fraction_completed = 0.3524
        self.widget.upsert_task(task)

        assert self.widget.rowCount() == 1
        assert self.widget.item(0, 1).text() == 'whisper-french.mp3'
        assert self.widget.item(0, 2).text() == 'In Progress (35%)'


@pytest.mark.skipif(platform.system() == 'Windows')
class TestRecordingTranscriberWidget:
    def test_should_set_window_title(self, qtbot: QtBot):
        widget = RecordingTranscriberWidget()
        qtbot.add_widget(widget)
        assert widget.windowTitle() == 'Live Recording'

    def test_should_transcribe(self, qtbot):
        widget = RecordingTranscriberWidget()
        qtbot.add_widget(widget)

        def assert_text_box_contains_text():
            assert len(widget.text_box.toPlainText()) > 0

        with patch('sounddevice.InputStream', side_effect=MockInputStream), patch('sounddevice.check_input_settings'):
            widget.record_button.click()
            qtbot.wait_until(callback=assert_text_box_contains_text, timeout=60 * 1000)

        with qtbot.wait_signal(widget.transcription_thread.finished, timeout=60 * 1000):
            widget.stop_recording()

        assert 'Welcome to Passe' in widget.text_box.toPlainText()


class TestHuggingFaceSearchLineEdit:
    def test_should_update_selected_model_on_type(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit()
        qtbot.add_widget(widget)

        mock_model_selected = Mock()
        widget.model_selected.connect(mock_model_selected)

        self._set_text_and_wait_response(qtbot, widget)
        mock_model_selected.assert_called_with('openai/whisper-tiny')

    def test_should_show_list_of_models(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit()
        qtbot.add_widget(widget)

        self._set_text_and_wait_response(qtbot, widget)

        assert widget.popup.count() > 0
        assert 'openai/whisper-tiny' in widget.popup.item(0).text()

    def test_should_select_model_from_list(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit()
        qtbot.add_widget(widget)

        mock_model_selected = Mock()
        widget.model_selected.connect(mock_model_selected)

        self._set_text_and_wait_response(qtbot, widget)

        # press down arrow and enter to select next item
        QApplication.sendEvent(widget.popup,
                               QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))
        QApplication.sendEvent(widget.popup,
                               QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier))

        mock_model_selected.assert_called_with('openai/whisper-tiny.en')

    @staticmethod
    def _set_text_and_wait_response(qtbot: QtBot, widget: HuggingFaceSearchLineEdit):
        with qtbot.wait_signal(widget.network_manager.finished, timeout=30 * 1000):
            widget.setText('openai/whisper-tiny')
            widget.textEdited.emit('openai/whisper-tiny')


class TestTranscriptionOptionsGroupBox:
    def test_should_update_model_type(self, qtbot):
        widget = TranscriptionOptionsGroupBox()
        qtbot.add_widget(widget)

        mock_transcription_options_changed = Mock()
        widget.transcription_options_changed.connect(mock_transcription_options_changed)

        widget.model_type_combo_box.setCurrentIndex(1)

        transcription_options: TranscriptionOptions = mock_transcription_options_changed.call_args[0][0]
        assert transcription_options.model.model_type == ModelType.WHISPER_CPP
