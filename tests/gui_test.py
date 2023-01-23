import logging
import multiprocessing
import os.path
import pathlib
import platform
from typing import List
from unittest.mock import Mock, patch

import pytest
import sounddevice
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QValidator, QKeyEvent
from PyQt6.QtWidgets import QPushButton, QToolBar, QTableWidget, QApplication, QMessageBox
from _pytest.fixtures import SubRequest
from pytestqt.qtbot import QtBot

from buzz.__version__ import VERSION
from buzz.cache import TasksCache
from buzz.gui import (AboutDialog, AdvancedSettingsDialog, AudioDevicesComboBox, DownloadModelProgressDialog,
                      FileTranscriberWidget, LanguagesComboBox, MainWindow,
                      RecordingTranscriberWidget,
                      TemperatureValidator, TextDisplayBox,
                      TranscriptionTasksTableWidget, TranscriptionViewerWidget, HuggingFaceSearchLineEdit,
                      TranscriptionOptionsGroupBox)
from buzz.model_loader import ModelType
from buzz.transcriber import (FileTranscriptionOptions, FileTranscriptionTask,
                              Segment, TranscriptionOptions)
from tests.mock_sounddevice import MockInputStream, mock_query_devices
from .mock_qt import MockNetworkAccessManager, MockNetworkReply

if platform.system() == 'Linux':
    multiprocessing.set_start_method('spawn')


@pytest.fixture(scope='module', autouse=True)
def audio_setup():
    with patch('sounddevice.query_devices') as query_devices_mock, \
            patch('sounddevice.InputStream', side_effect=MockInputStream), \
            patch('sounddevice.check_input_settings'):
        query_devices_mock.return_value = mock_query_devices
        sounddevice.default.device = 3, 4
        yield


class TestLanguagesComboBox:

    def test_should_show_sorted_whisper_languages(self, qtbot):
        languages_combox_box = LanguagesComboBox('en')
        qtbot.add_widget(languages_combox_box)
        assert languages_combox_box.itemText(0) == 'Detect Language'
        assert languages_combox_box.itemText(10) == 'Belarusian'
        assert languages_combox_box.itemText(20) == 'Dutch'
        assert languages_combox_box.itemText(30) == 'Gujarati'
        assert languages_combox_box.itemText(40) == 'Japanese'
        assert languages_combox_box.itemText(50) == 'Lithuanian'

    def test_should_select_en_as_default_language(self, qtbot):
        languages_combox_box = LanguagesComboBox('en')
        qtbot.add_widget(languages_combox_box)
        assert languages_combox_box.currentText() == 'English'

    def test_should_select_detect_language_as_default(self, qtbot):
        languages_combo_box = LanguagesComboBox(None)
        qtbot.add_widget(languages_combo_box)
        assert languages_combo_box.currentText() == 'Detect Language'


class TestAudioDevicesComboBox:
    def test_get_devices(self):
        audio_devices_combo_box = AudioDevicesComboBox()

        assert audio_devices_combo_box.itemText(0) == 'Background Music'
        assert audio_devices_combo_box.itemText(1) == 'Background Music (UI Sounds)'
        assert audio_devices_combo_box.itemText(2) == 'BlackHole 2ch'
        assert audio_devices_combo_box.itemText(3) == 'MacBook Pro Microphone'
        assert audio_devices_combo_box.itemText(4) == 'Null Audio Device'

        assert audio_devices_combo_box.currentText() == 'MacBook Pro Microphone'

    def test_select_default_mic_when_no_default(self):
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


@pytest.fixture()
def tasks_cache(tmp_path, request: SubRequest):
    cache = TasksCache(cache_dir=str(tmp_path))
    if hasattr(request, 'param'):
        tasks: List[FileTranscriptionTask] = request.param
        cache.save(tasks)
    yield cache
    cache.clear()


def get_test_asset(filename: str):
    return os.path.join(os.path.dirname(__file__), '../testdata/', filename)


mock_tasks = [
    FileTranscriptionTask(file_path='', transcription_options=TranscriptionOptions(),
                          file_transcription_options=FileTranscriptionOptions(file_paths=[]), model_path='',
                          status=FileTranscriptionTask.Status.COMPLETED),
    FileTranscriptionTask(file_path='', transcription_options=TranscriptionOptions(),
                          file_transcription_options=FileTranscriptionOptions(file_paths=[]), model_path='',
                          status=FileTranscriptionTask.Status.CANCELED),
    FileTranscriptionTask(file_path='', transcription_options=TranscriptionOptions(),
                          file_transcription_options=FileTranscriptionOptions(file_paths=[]), model_path='',
                          status=FileTranscriptionTask.Status.FAILED),
]


class TestMainWindow:

    def test_should_set_window_title_and_icon(self, qtbot):
        window = MainWindow()
        qtbot.add_widget(window)
        assert window.windowTitle() == 'Buzz'
        assert window.windowIcon().pixmap(QSize(64, 64)).isNull() is False
        window.close()

    @pytest.mark.xfail(condition=platform.system() == 'Windows', reason='Timing out')
    def test_should_run_transcription_task(self, qtbot: QtBot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        self._start_new_transcription(window)

        open_transcript_action = self._get_toolbar_action(window, 'Open Transcript')
        assert open_transcript_action.isEnabled() is False

        table_widget: QTableWidget = window.findChild(QTableWidget)
        qtbot.wait_until(self._assert_task_status(table_widget, 0, 'Completed'), timeout=2 * 60 * 1000)

        table_widget.setCurrentIndex(table_widget.indexFromItem(table_widget.item(0, 1)))
        assert open_transcript_action.isEnabled()

    def test_should_run_and_cancel_transcription_task(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        self._start_new_transcription(window)

        table_widget: QTableWidget = window.findChild(QTableWidget)

        def assert_task_in_progress():
            assert table_widget.rowCount() > 0
            assert table_widget.item(0, 1).text() == 'whisper-french.mp3'
            assert 'In Progress' in table_widget.item(0, 2).text()

        qtbot.wait_until(assert_task_in_progress, timeout=2 * 60 * 1000)

        # Stop task in progress
        table_widget.selectRow(0)
        window.toolbar.stop_transcription_action.trigger()

        qtbot.wait_until(self._assert_task_status(table_widget, 0, 'Canceled'), timeout=60 * 1000)

        table_widget.selectRow(0)
        assert window.toolbar.stop_transcription_action.isEnabled() is False
        assert window.toolbar.open_transcript_action.isEnabled() is False

        window.close()

    @pytest.mark.parametrize('tasks_cache', [mock_tasks], indirect=True)
    def test_should_load_tasks_from_cache(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        table_widget: QTableWidget = window.findChild(QTableWidget)
        assert table_widget.rowCount() == 3

        assert table_widget.item(0, 2).text() == 'Completed'
        table_widget.selectRow(0)
        assert window.toolbar.open_transcript_action.isEnabled()

        assert table_widget.item(1, 2).text() == 'Canceled'
        table_widget.selectRow(1)
        assert window.toolbar.open_transcript_action.isEnabled() is False

        assert table_widget.item(2, 2).text() == 'Failed'
        table_widget.selectRow(2)
        assert window.toolbar.open_transcript_action.isEnabled() is False
        window.close()

    @pytest.mark.parametrize('tasks_cache', [mock_tasks], indirect=True)
    def test_should_clear_history_with_rows_selected(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)

        table_widget: QTableWidget = window.findChild(QTableWidget)
        table_widget.selectAll()

        with patch('PyQt6.QtWidgets.QMessageBox.question') as question_message_box_mock:
            question_message_box_mock.return_value = QMessageBox.StandardButton.Yes
            window.toolbar.clear_history_action.trigger()

        assert table_widget.rowCount() == 0
        window.close()

    @pytest.mark.parametrize('tasks_cache', [mock_tasks], indirect=True)
    def test_should_have_clear_history_action_disabled_with_no_rows_selected(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        assert window.toolbar.clear_history_action.isEnabled() is False
        window.close()

    @pytest.mark.parametrize('tasks_cache', [mock_tasks], indirect=True)
    def test_should_open_transcription_viewer(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        table_widget: QTableWidget = window.findChild(QTableWidget)

        table_widget.selectRow(0)

        window.toolbar.open_transcript_action.trigger()

        transcription_viewer = window.findChild(TranscriptionViewerWidget)
        assert transcription_viewer is not None

        window.close()

    @pytest.mark.parametrize('tasks_cache', [mock_tasks], indirect=True)
    def test_should_have_open_transcript_action_disabled_with_no_rows_selected(self, qtbot, tasks_cache):
        window = MainWindow(tasks_cache=tasks_cache)
        qtbot.add_widget(window)

        assert window.toolbar.open_transcript_action.isEnabled() is False
        window.close()

    @staticmethod
    def _start_new_transcription(window: MainWindow):
        with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileNames') as open_file_names_mock:
            open_file_names_mock.return_value = ([get_test_asset('whisper-french.mp3')], '')
            new_transcription_action = TestMainWindow._get_toolbar_action(window, 'New Transcription')
            new_transcription_action.trigger()

        file_transcriber_widget: FileTranscriberWidget = window.findChild(FileTranscriberWidget)
        run_button: QPushButton = file_transcriber_widget.findChild(QPushButton)
        run_button.click()

    @staticmethod
    def _assert_task_status(table_widget: QTableWidget, row_index: int, expected_status: str):
        def assert_task_canceled():
            assert table_widget.rowCount() > 0
            assert table_widget.item(row_index, 1).text() == 'whisper-french.mp3'
            assert table_widget.item(row_index, 2).text() == expected_status

        return assert_task_canceled

    @staticmethod
    def _get_toolbar_action(window: MainWindow, text: str):
        toolbar: QToolBar = window.findChild(QToolBar)
        return [action for action in toolbar.actions() if action.text() == text][0]


class TestFileTranscriberWidget:
    def test_should_set_window_title(self, qtbot: QtBot):
        widget = FileTranscriberWidget(
            file_paths=['testdata/whisper-french.mp3'], parent=None)
        qtbot.add_widget(widget)
        assert widget.windowTitle() == 'whisper-french.mp3'

    def test_should_emit_triggered_event(self, qtbot: QtBot):
        widget = FileTranscriberWidget(
            file_paths=['testdata/whisper-french.mp3'], parent=None)
        qtbot.add_widget(widget)

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
    def test_should_check_for_updates(self, qtbot: QtBot):
        reply = MockNetworkReply(data={'name': 'v' + VERSION})
        manager = MockNetworkAccessManager(reply=reply)
        dialog = AboutDialog(network_access_manager=manager)
        qtbot.add_widget(dialog)

        mock_message_box_information = Mock()
        QMessageBox.information = mock_message_box_information

        with qtbot.wait_signal(dialog.network_access_manager.finished):
            dialog.check_updates_button.click()

        mock_message_box_information.assert_called_with(dialog, '', "You're up to date!")


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

    def test_should_display_segments(self, qtbot: QtBot):
        widget = TranscriptionViewerWidget(
            transcription_task=FileTranscriptionTask(
                id=0,
                file_path='testdata/whisper-french.mp3',
                file_transcription_options=FileTranscriptionOptions(
                    file_paths=['testdata/whisper-french.mp3']),
                transcription_options=TranscriptionOptions(),
                segments=[Segment(40, 299, 'Bien'),
                          Segment(299, 329, 'venue dans')],
                model_path=''), open_transcription_output=False)
        qtbot.add_widget(widget)

        assert widget.windowTitle() == 'whisper-french.mp3'

        text_display_box = widget.findChild(TextDisplayBox)
        assert isinstance(text_display_box, TextDisplayBox)
        assert text_display_box.toPlainText(
        ) == '00:00:00.040 --> 00:00:00.299\nBien\n\n00:00:00.299 --> 00:00:00.329\nvenue dans'

    def test_should_export_segments(self, tmp_path: pathlib.Path, qtbot: QtBot):
        widget = TranscriptionViewerWidget(
            transcription_task=FileTranscriptionTask(
                id=0,
                file_path='testdata/whisper-french.mp3',
                file_transcription_options=FileTranscriptionOptions(
                    file_paths=['testdata/whisper-french.mp3']),
                transcription_options=TranscriptionOptions(),
                segments=[Segment(40, 299, 'Bien'),
                          Segment(299, 329, 'venue dans')],
                model_path=''), open_transcription_output=False)
        qtbot.add_widget(widget)

        export_button = widget.findChild(QPushButton)
        assert isinstance(export_button, QPushButton)

        output_file_path = tmp_path / 'whisper.txt'
        with patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName') as save_file_name_mock:
            save_file_name_mock.return_value = (str(output_file_path), '')
            export_button.menu().actions()[0].trigger()

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert 'Bien venue dans' in output_file.read()


class TestTranscriptionTasksTableWidget:

    def test_upsert_task(self, qtbot: QtBot):
        widget = TranscriptionTasksTableWidget()
        qtbot.add_widget(widget)

        task = FileTranscriptionTask(id=0, file_path='testdata/whisper-french.mp3',
                                     transcription_options=TranscriptionOptions(),
                                     file_transcription_options=FileTranscriptionOptions(
                                         file_paths=['testdata/whisper-french.mp3']), model_path='',
                                     status=FileTranscriptionTask.Status.QUEUED)

        widget.upsert_task(task)

        assert widget.rowCount() == 1
        assert widget.item(0, 1).text() == 'whisper-french.mp3'
        assert widget.item(0, 2).text() == 'Queued'

        task.status = FileTranscriptionTask.Status.IN_PROGRESS
        task.fraction_completed = 0.3524
        widget.upsert_task(task)

        assert widget.rowCount() == 1
        assert widget.item(0, 1).text() == 'whisper-french.mp3'
        assert widget.item(0, 2).text() == 'In Progress (35%)'


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

        widget.record_button.click()
        qtbot.wait_until(callback=assert_text_box_contains_text, timeout=60 * 1000)

        with qtbot.wait_signal(widget.transcription_thread.finished, timeout=60 * 1000):
            widget.stop_recording()

        assert 'Welcome to Passe' in widget.text_box.toPlainText()


class TestHuggingFaceSearchLineEdit:
    def test_should_update_selected_model_on_type(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit(network_access_manager=self.network_access_manager())
        qtbot.add_widget(widget)

        mock_model_selected = Mock()
        widget.model_selected.connect(mock_model_selected)

        self._set_text_and_wait_response(qtbot, widget)
        mock_model_selected.assert_called_with('openai/whisper-tiny')

    def test_should_show_list_of_models(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit(network_access_manager=self.network_access_manager())
        qtbot.add_widget(widget)

        self._set_text_and_wait_response(qtbot, widget)

        assert widget.popup.count() > 0
        assert 'openai/whisper-tiny' in widget.popup.item(0).text()

    def test_should_select_model_from_list(self, qtbot: QtBot):
        widget = HuggingFaceSearchLineEdit(network_access_manager=self.network_access_manager())
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
    def network_access_manager():
        reply = MockNetworkReply(data=[{'id': 'openai/whisper-tiny'}, {'id': 'openai/whisper-tiny.en'}])
        return MockNetworkAccessManager(reply=reply)

    @staticmethod
    def _set_text_and_wait_response(qtbot: QtBot, widget: HuggingFaceSearchLineEdit):
        with qtbot.wait_signal(widget.network_manager.finished):
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
