from buzz.model_loader import ModelType
from buzz.transcriber.transcriber import Task, TranscriptionOptions
from buzz.widgets.transcriber.transcription_options_group_box import (
    TranscriptionOptionsGroupBox,
)


def test_selecting_funasr_forces_transcription_and_disables_unsupported_controls(
    qtbot,
):
    options = TranscriptionOptions(
        task=Task.TRANSLATE,
        initial_prompt="must be cleared",
    )
    widget = TranscriptionOptionsGroupBox(default_transcription_options=options)
    qtbot.add_widget(widget)
    widget.show()

    widget.on_model_type_changed(ModelType.FUNASR_API)

    assert options.task == Task.TRANSCRIBE
    assert options.initial_prompt == ""
    assert not widget.tasks_combo_box.isEnabled()
    assert not widget.openai_access_token_edit.isVisible()
    assert not widget.advanced_settings_dialog.initial_prompt_text_edit.isEnabled()
    assert (
        widget.advanced_settings_dialog.initial_prompt_text_edit.toPlainText() == ""
    )


def test_switching_from_funasr_reenables_supported_controls(qtbot):
    options = TranscriptionOptions()
    widget = TranscriptionOptionsGroupBox(default_transcription_options=options)
    qtbot.add_widget(widget)

    widget.on_model_type_changed(ModelType.FUNASR_API)
    widget.on_model_type_changed(ModelType.OPEN_AI_WHISPER_API)

    assert widget.tasks_combo_box.isEnabled()
    assert widget.advanced_settings_dialog.initial_prompt_text_edit.isEnabled()
