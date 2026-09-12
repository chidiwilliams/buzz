from unittest.mock import Mock, patch

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit

from buzz.model_loader import TranscriptionModel
from buzz.transcriber.transcriber import Task
from buzz.widgets.preferences_dialog.folder_watch_preferences_widget import (
    FolderWatchPreferencesWidget,
)
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.preferences_dialog.models.folder_watch_preferences import (
    FolderWatchPreferences,
)


class TestFolderWatchPreferencesWidget:
    def test_edit_folder_watch_preferences(self, qtbot):
        widget = FolderWatchPreferencesWidget(
            config=FolderWatchPreferences(
                enabled=False,
                input_directory="",
                output_directory="",
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=TranscriptionModel.default(),
                    word_level_timings=False,
                    extract_speech=False,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )
        mock_config_changed = Mock()
        widget.config_changed.connect(mock_config_changed)
        qtbot.add_widget(widget)

        checkbox = widget.findChild(QCheckBox, "EnableFolderWatchCheckbox")
        input_folder_line_edit = widget.findChild(QLineEdit, "InputFolderLineEdit")
        output_folder_line_edit = widget.findChild(QLineEdit, "OutputFolderLineEdit")

        assert not checkbox.isChecked()
        assert input_folder_line_edit.text() == ""
        assert output_folder_line_edit.text() == ""
        assert not input_folder_line_edit.isEnabled()
        assert not output_folder_line_edit.isEnabled()

        checkbox.setChecked(True)
        assert input_folder_line_edit.isEnabled()
        assert output_folder_line_edit.isEnabled()
        input_folder_line_edit.setText("test/input/folder")
        output_folder_line_edit.setText("test/output/folder")

        last_config_changed_call = mock_config_changed.call_args_list[-1]
        assert last_config_changed_call[0][0].enabled
        assert last_config_changed_call[0][0].input_directory == "test/input/folder"
        assert last_config_changed_call[0][0].output_directory == "test/output/folder"

    def test_rejects_output_folder_inside_input_folder(self, qtbot, tmp_path):
        input_dir = tmp_path / "watch"
        output_dir = input_dir / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        widget = FolderWatchPreferencesWidget(
            config=FolderWatchPreferences(
                enabled=True,
                input_directory=str(input_dir),
                output_directory="",
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=TranscriptionModel.default(),
                    word_level_timings=False,
                    extract_speech=False,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )
        qtbot.add_widget(widget)

        output_folder_line_edit = widget.findChild(QLineEdit, "OutputFolderLineEdit")

        with patch(
            "buzz.widgets.preferences_dialog.folder_watch_preferences_widget"
            ".QMessageBox.warning"
        ) as mock_warning:
            output_folder_line_edit.setText(str(output_dir))
            widget.on_output_folder_editing_finished()

        mock_warning.assert_called_once()
        assert widget.config.output_directory == ""
        assert output_folder_line_edit.text() == ""

    def test_delete_processed_files_checkbox(self, qtbot):
        widget = FolderWatchPreferencesWidget(
            config=FolderWatchPreferences(
                enabled=False,
                input_directory="",
                output_directory="",
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=TranscriptionModel.default(),
                    word_level_timings=False,
                    extract_speech=False,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )
        mock_config_changed = Mock()
        widget.config_changed.connect(mock_config_changed)
        qtbot.add_widget(widget)

        delete_checkbox = widget.findChild(QCheckBox, "DeleteProcessedFilesCheckbox")
        assert delete_checkbox is not None
        assert not delete_checkbox.isChecked()

        delete_checkbox.setChecked(True)

        last_config = mock_config_changed.call_args_list[-1][0][0]
        assert last_config.delete_processed_files is True

        delete_checkbox.setChecked(False)

        last_config = mock_config_changed.call_args_list[-1][0][0]
        assert last_config.delete_processed_files is False

    def test_speaker_identification_options(self, qtbot):
        widget = FolderWatchPreferencesWidget(
            config=FolderWatchPreferences(
                enabled=True,
                input_directory="",
                output_directory="",
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=TranscriptionModel.default(),
                    word_level_timings=False,
                    extract_speech=False,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
            ),
        )
        mock_config_changed = Mock()
        widget.config_changed.connect(mock_config_changed)
        qtbot.add_widget(widget)

        title_label = widget.findChild(QLabel, "SpeakerIdentificationLabel")
        identify_checkbox = widget.findChild(QCheckBox, "IdentifySpeakersCheckbox")
        diarizer_combo_box = widget.findChild(QComboBox, "SpeakerDiarizerComboBox")
        speaker_count_combo_box = widget.findChild(QComboBox, "SpeakerCountComboBox")
        merge_checkbox = widget.findChild(QCheckBox, "MergeSpeakerSentencesCheckbox")

        # The title is translated, so only its styling is asserted here
        assert title_label.font().weight() == QFont.Weight.Bold

        assert not identify_checkbox.isChecked()
        assert not diarizer_combo_box.isEnabled()
        assert not speaker_count_combo_box.isEnabled()
        assert not merge_checkbox.isEnabled()

        identify_checkbox.setChecked(True)

        assert diarizer_combo_box.isEnabled()
        assert speaker_count_combo_box.isEnabled()
        assert merge_checkbox.isEnabled()

        last_config = mock_config_changed.call_args_list[-1][0][0]
        assert last_config.identify_speakers is True
        assert last_config.speaker_diarizer == "msdd"
        assert last_config.speaker_count is None
        assert last_config.merge_speaker_sentences is True

        speaker_count_combo_box.setCurrentIndex(
            speaker_count_combo_box.findData(3)
        )
        assert mock_config_changed.call_args_list[-1][0][0].speaker_count == 3

        merge_checkbox.setChecked(False)
        assert (
            mock_config_changed.call_args_list[-1][0][0].merge_speaker_sentences
            is False
        )

        # The speaker count is an MSDD-only option
        diarizer_combo_box.setCurrentIndex(
            diarizer_combo_box.findData("sortformer")
        )
        last_config = mock_config_changed.call_args_list[-1][0][0]
        assert last_config.speaker_diarizer == "sortformer"
        assert not speaker_count_combo_box.isEnabled()

    def test_speaker_options_disabled_when_folder_watch_disabled(self, qtbot):
        widget = FolderWatchPreferencesWidget(
            config=FolderWatchPreferences(
                enabled=False,
                input_directory="",
                output_directory="",
                file_transcription_options=FileTranscriptionPreferences(
                    language=None,
                    task=Task.TRANSCRIBE,
                    model=TranscriptionModel.default(),
                    word_level_timings=False,
                    extract_speech=False,
                    initial_prompt="",
                    enable_llm_translation=False,
                    llm_model="",
                    llm_prompt="",
                    output_formats=set(),
                ),
                identify_speakers=True,
            ),
        )
        qtbot.add_widget(widget)

        identify_checkbox = widget.findChild(QCheckBox, "IdentifySpeakersCheckbox")
        diarizer_combo_box = widget.findChild(QComboBox, "SpeakerDiarizerComboBox")

        assert identify_checkbox.isChecked()
        assert not identify_checkbox.isEnabled()
        assert not diarizer_combo_box.isEnabled()

        widget.findChild(QCheckBox, "EnableFolderWatchCheckbox").setChecked(True)

        assert identify_checkbox.isEnabled()
        assert diarizer_combo_box.isEnabled()
