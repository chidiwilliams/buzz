from unittest.mock import Mock

from PyQt6.QtWidgets import QCheckBox, QLineEdit

from buzz.model_loader import TranscriptionModel
from buzz.transcriber.transcriber import Task, DEFAULT_WHISPER_TEMPERATURE
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
                    temperature=DEFAULT_WHISPER_TEMPERATURE,
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

        checkbox.setChecked(True)
        input_folder_line_edit.setText("test/input/folder")
        output_folder_line_edit.setText("test/output/folder")

        last_config_changed_call = mock_config_changed.call_args_list[-1]
        assert last_config_changed_call[0][0].enabled
        assert last_config_changed_call[0][0].input_directory == "test/input/folder"
        assert last_config_changed_call[0][0].output_directory == "test/output/folder"
