import os
import os
import pathlib
from typing import Any, Callable
from unittest.mock import Mock, patch

import pytest
import sounddevice
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtGui import (QValidator)
from PyQt6.QtWidgets import (QPushButton)
from pytestqt.qtbot import QtBot

from buzz.gui import (AboutDialog, AdvancedSettingsDialog, Application,
                      AudioDevicesComboBox, DownloadModelProgressDialog,
                      FileTranscriberWidget, LanguagesComboBox, MainWindow,
                      ModelComboBox, TemperatureValidator,
                      TextDisplayBox, TranscriberProgressDialog, TranscriptionViewerWidget)
from buzz.transcriber import FileTranscriptionOptions, Segment, TranscriptionOptions, Model


class TestApplication:
    app = Application()

    def test_should_show_window_title(self):
        assert len(self.app.windows) == 1
        assert self.app.windows[0].windowTitle() == 'Live Recording - Buzz'

    def test_should_open_a_new_import_file_window(self):
        main_window = self.app.windows[0]
        import_file_action = main_window.file_menu.actions()[0]

        assert import_file_action.text() == '&Import Audio File...'

        with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName') as open_file_name_mock:
            open_file_name_mock.return_value = ('/a/b/c.mp3', '')
            import_file_action.trigger()
            assert len(self.app.windows) == 2

            new_window = self.app.windows[1]
            assert new_window.windowTitle() == 'c.mp3 - Buzz'


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


class TestModelComboBox:
    model_combo_box = ModelComboBox(
        default_model=Model.WHISPER_CPP_BASE, parent=None)

    def test_should_show_qualities(self):
        assert self.model_combo_box.itemText(0) == 'Whisper - Tiny'
        assert self.model_combo_box.itemText(1) == 'Whisper - Base'
        assert self.model_combo_box.itemText(2) == 'Whisper - Small'
        assert self.model_combo_box.itemText(3) == 'Whisper - Medium'

    def test_should_select_default_model(self):
        assert self.model_combo_box.currentText() == 'Whisper.cpp - Base'


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


class TestTranscriberProgressDialog:
    dialog = TranscriberProgressDialog(
        file_path='/a/b/c.txt', total_size=1234567, parent=None)

    # Should not be able to interact with the transcriber widget while transcription
    # is already ongoing. This also prevents an issue with the application
    # not closing when the transcriber widget is closed before the progress dialog
    def test_should_be_a_window_modal(self):
        assert self.dialog.windowModality() == Qt.WindowModality.WindowModal

    def test_should_show_dialog(self):
        assert self.dialog.labelText() == 'Processing c.txt (0%, unknown time remaining)'

    def test_should_update_label_on_progress(self):
        self.dialog.update_progress(12345)
        assert self.dialog.labelText().startswith('Processing c.txt (1.00%')

        self.dialog.update_progress(123456)
        assert self.dialog.labelText().startswith('Processing c.txt (10.00%')


class TestDownloadModelProgressDialog:
    def test_should_show_dialog(self, qtbot: QtBot):
        dialog = DownloadModelProgressDialog(total_size=1234567, parent=None)
        qtbot.add_widget(dialog)
        assert dialog.labelText() == 'Downloading resources (0%, unknown time remaining)'

    def test_should_update_label_on_progress(self, qtbot: QtBot):
        dialog = DownloadModelProgressDialog(total_size=1234567, parent=None)
        qtbot.add_widget(dialog)
        dialog.setValue(0)

        dialog.setValue(12345)
        assert dialog.labelText().startswith(
            'Downloading resources (1.00%')

        dialog.setValue(123456)
        assert dialog.labelText().startswith(
            'Downloading resources (10.00%')

    # Other windows should not be processing while models are being downloaded
    def test_should_be_an_application_modal(self, qtbot: QtBot):
        dialog = DownloadModelProgressDialog(total_size=1234567, parent=None)
        qtbot.add_widget(dialog)
        assert dialog.windowModality() == Qt.WindowModality.ApplicationModal


class TestMainWindow:
    def test_should_init(self):
        main_window = MainWindow(title='', w=200, h=200, parent=None)
        assert main_window is not None


def wait_until(callback: Callable[[], Any], timeout=0):
    while True:
        try:
            QCoreApplication.processEvents()
            callback()
            return
        except AssertionError:
            pass


class TestFileTranscriberWidget:
    @pytest.mark.skip(reason='Waiting for signal crashes process on Windows and Mac')
    def test_should_transcribe(self, qtbot: QtBot):
        widget = FileTranscriberWidget(
            file_path='testdata/whisper-french.mp3', parent=None)
        qtbot.addWidget(widget)

        # Waiting for a "transcribed" signal seems to work more consistently
        # than checking for the opening of a TranscriptionViewerWidget.
        # See also: https://github.com/pytest-dev/pytest-qt/issues/313
        with qtbot.wait_signal(widget.transcribed, timeout=30 * 1000):
            qtbot.mouseClick(widget.run_button, Qt.MouseButton.LeftButton)

        transcription_viewer = widget.findChild(TranscriptionViewerWidget)
        assert isinstance(transcription_viewer, TranscriptionViewerWidget)
        assert len(transcription_viewer.segments) > 0

    @pytest.mark.skip(
        reason="transcription_started callback sometimes not getting called until all progress events are emitted")
    def test_should_transcribe_and_stop(self, qtbot: QtBot, tmp_path: pathlib.Path):
        widget = FileTranscriberWidget(
            file_path='testdata/whisper-french-long.mp3', parent=None)
        qtbot.addWidget(widget)

        output_file_path = tmp_path / 'whisper.txt'

        with (patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName') as save_file_name_mock):
            save_file_name_mock.return_value = (str(output_file_path), '')
            widget.run_button.click()

        def transcription_started():
            QCoreApplication.processEvents()
            assert widget.transcriber_progress_dialog is not None
            assert widget.transcriber_progress_dialog.value() > 0

        qtbot.wait_until(transcription_started, timeout=30 * 1000)

        widget.transcriber_progress_dialog.close()

        assert os.path.isfile(output_file_path) is False
        assert widget.run_button.isEnabled()


class TestAboutDialog:
    def test_should_create(self):
        dialog = AboutDialog()
        assert dialog is not None


class TestAdvancedSettingsDialog:
    def test_should_update_advanced_settings(self, qtbot: QtBot):
        dialog = AdvancedSettingsDialog(
            transcription_options=TranscriptionOptions(temperature=(0.0, 0.8), initial_prompt='prompt',
                                                       model=Model.WHISPER_CPP_BASE))
        qtbot.add_widget(dialog)

        transcription_options_mock = Mock()
        dialog.transcription_options_changed.connect(transcription_options_mock)

        assert dialog.windowTitle() == 'Advanced Settings'
        assert dialog.temperature_line_edit.text() == '0.0, 0.8'
        assert dialog.initial_prompt_text_edit.toPlainText() == 'prompt'

        dialog.temperature_line_edit.setText('0.0, 0.8, 1.0')
        dialog.initial_prompt_text_edit.setPlainText('new prompt')

        assert transcription_options_mock.call_args[0][0].temperature == (0.0, 0.8, 1.0)
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
        file_transcription_options=FileTranscriptionOptions(
            file_path='testdata/whisper-french.mp3'),
        transcription_options=TranscriptionOptions(),
        segments=[Segment(40, 299, 'Bien'), Segment(299, 329, 'venue dans')])

    def test_should_display_segments(self, qtbot: QtBot):
        qtbot.add_widget(self.widget)

        assert self.widget.windowTitle() == 'Transcription - whisper-french.mp3'

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
