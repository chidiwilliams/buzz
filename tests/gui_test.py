from unittest.mock import Mock
from pytestqt.qtbot import QtBot
import pathlib
from unittest.mock import Mock, patch

import sounddevice
from PyQt6.QtCore import QCoreApplication, Qt, pyqtBoundSignal

from buzz.gui import (AboutDialog, Application, AudioDevicesComboBox,
                      DownloadModelProgressDialog, FileTranscriberWidget,
                      LanguagesComboBox, MainWindow, OutputFormatsComboBox,
                      Quality, QualityComboBox, RecordingTranscriberWidget, Settings,
                      TranscriberProgressDialog)
from buzz.transcriber import OutputFormat
from .sd import sounddevice_mocks


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


class TestQualityComboBox:
    quality_combo_box = QualityComboBox(
        default_quality=Quality.MEDIUM, parent=None)

    def test_should_show_qualities(self):
        assert self.quality_combo_box.itemText(0) == 'Very Low'
        assert self.quality_combo_box.itemText(1) == 'Low'
        assert self.quality_combo_box.itemText(2) == 'Medium'
        assert self.quality_combo_box.itemText(3) == 'High'

    def test_should_select_default_quality(self):
        assert self.quality_combo_box.currentText() == 'Medium'


class TestAudioDevicesComboBox:
    def test_get_devices(self):
        with sounddevice_mocks():
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
        with sounddevice_mocks():
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
    dialog = DownloadModelProgressDialog(total_size=1234567, parent=None)

    def test_should_show_dialog(self):
        assert self.dialog.labelText() == 'Downloading resources (0%, unknown time remaining)'

    def test_should_update_label_on_progress(self):
        self.dialog.setValue(0)

        self.dialog.setValue(12345)
        assert self.dialog.labelText().startswith(
            'Downloading resources (1.00%')

        self.dialog.setValue(123456)
        assert self.dialog.labelText().startswith(
            'Downloading resources (10.00%')

    # Other windows should not be processing while models are being downloaded
    def test_should_be_an_application_modal(self):
        assert self.dialog.windowModality() == Qt.WindowModality.ApplicationModal


class TestFormatsComboBox:
    def test_should_have_items(self):
        formats_combo_box = OutputFormatsComboBox(OutputFormat.TXT, None)
        assert formats_combo_box.itemText(0) == '.txt'
        assert formats_combo_box.itemText(1) == '.srt'
        assert formats_combo_box.itemText(2) == '.vtt'


class TestMainWindow:
    def test_should_init(self):
        main_window = MainWindow(title='', w=200, h=200, parent=None)
        assert main_window is not None


class TestFileTranscriberWidget:
    def test_should_transcribe(self, qtbot, tmp_path: pathlib.Path):
        widget = FileTranscriberWidget(
            file_path='testdata/whisper-french.mp3', parent=None)
        qtbot.addWidget(widget)

        output_file_path = tmp_path / 'whisper.txt'

        with patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName') as save_file_name_mock:
            save_file_name_mock.return_value = (output_file_path, '')
            widget.run_button.click()

        wait_signal_while_processing(widget.transcribed)

        output_file = open(output_file_path, 'r', encoding='utf-8')
        assert 'Bienvenue dans Passe-Relle, un podcast' in output_file.read()


def wait_signal_while_processing(signal: pyqtBoundSignal):
    mock = Mock()
    signal.connect(mock)
    while True:
        QCoreApplication.processEvents()
        if mock.call_count > 0:
            break


class TestRecordingTranscriberWidget:
    def test_should_transcribe(self, qtbot: QtBot):
        with sounddevice_mocks():
            widget = RecordingTranscriberWidget()

            assert widget.audio_devices_combo_box.currentText() == 'MacBook Pro Microphone'

            with qtbot.wait_signal(widget.transcription, timeout=30_000):
                widget.record_button.click()

            widget.record_button.click()
            assert 'Bienvenue dans Passe' in widget.text_box.toPlainText()


class TestSettings:
    def test_should_enable_ggml_inference(self):
        settings = Settings()
        settings.clear()

        assert settings.get_enable_ggml_inference() is False

        settings.set_enable_ggml_inference(True)
        assert settings.get_enable_ggml_inference() is True

        settings.set_enable_ggml_inference(False)
        assert settings.get_enable_ggml_inference() is False


class TestAboutDialog:
    def test_should_create(self):
        dialog = AboutDialog()
        assert dialog is not None
