import os
import tempfile
from unittest.mock import patch

import sounddevice
from PyQt6.QtCore import Qt

from gui import (Application, AudioDevicesComboBox,
                 DownloadModelProgressDialog, FileTranscriberWidget,
                 LanguagesComboBox, MainWindow, OutputFormatsComboBox, Quality, Settings,
                 QualityComboBox, TranscriberProgressDialog)
from transcriber import OutputFormat


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
    mock_query_devices = [
        {'name': 'Background Music', 'index': 0, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
         'default_low_output_latency': 0.008, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.064, 'default_samplerate': 8000.0},
        {'name': 'Background Music (UI Sounds)', 'index': 1, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.008, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.064, 'default_samplerate': 8000.0},
        {'name': 'BlackHole 2ch', 'index': 2, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.0013333333333333333, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.010666666666666666, 'default_samplerate': 48000.0},
        {'name': 'MacBook Pro Microphone', 'index': 3, 'hostapi': 0, 'max_input_channels': 1, 'max_output_channels': 0, 'default_low_input_latency': 0.034520833333333334,
                 'default_low_output_latency': 0.01, 'default_high_input_latency': 0.043854166666666666, 'default_high_output_latency': 0.1, 'default_samplerate': 48000.0},
        {'name': 'MacBook Pro Speakers', 'index': 4, 'hostapi': 0, 'max_input_channels': 0, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.0070416666666666666, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.016375, 'default_samplerate': 48000.0},
        {'name': 'Null Audio Device', 'index': 5, 'hostapi': 0, 'max_input_channels': 2, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.0014512471655328798, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.011609977324263039, 'default_samplerate': 44100.0},
        {'name': 'Multi-Output Device', 'index': 6, 'hostapi': 0, 'max_input_channels': 0, 'max_output_channels': 2, 'default_low_input_latency': 0.01,
                 'default_low_output_latency': 0.0033333333333333335, 'default_high_input_latency': 0.1, 'default_high_output_latency': 0.012666666666666666, 'default_samplerate': 48000.0},
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
    widget = FileTranscriberWidget(
        file_path='testdata/whisper-french.mp3', parent=None)

    def test_should_transcribe(self):
        output_file_path = os.path.join(
            tempfile.gettempdir(), 'whisper_cpp.txt')
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        with patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName') as save_file_name_mock:
            save_file_name_mock.return_value = (output_file_path, '')

            self.widget.run_button.click()
            if self.widget.file_transcriber is not None:
                self.widget.file_transcriber.join()

                output_file = open(output_file_path, 'r', encoding='utf-8')
                assert 'Bienvenue dans Passe-Relle, un podcast' in output_file.read()


class TestSettings:
    def test_should_enable_ggml_inference(self):
        settings = Settings()
        settings.clear()

        assert settings.get_enable_ggml_inference() is False
        settings.set_enable_ggml_inference(True)
        assert settings.get_enable_ggml_inference() is True
        settings.set_enable_ggml_inference(False)
        assert settings.get_enable_ggml_inference() is False
