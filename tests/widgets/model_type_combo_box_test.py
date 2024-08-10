import platform

import pytest

from buzz.widgets.model_type_combo_box import ModelTypeComboBox


class TestModelTypeComboBox:
    @pytest.mark.parametrize(
        "model_types",
        [
            pytest.param(
                [
                    "Whisper",
                    "Whisper.cpp",
                    "Hugging Face",
                    "Faster Whisper",
                    "OpenAI Whisper API",
                    # Faster Whisper is not available on macOS x86_64
                ] if not (platform.system() == "Darwin" and platform.machine() == "x86_64") else [
                    "Whisper",
                    "Whisper.cpp",
                    "Hugging Face",
                    "OpenAI Whisper API",
                ],
            ),
        ],
    )
    def test_should_display_items(self, qtbot, model_types):
        widget = ModelTypeComboBox()
        qtbot.add_widget(widget)

        assert widget.count() == len(model_types)
        for index, model_type in enumerate(model_types):
            assert widget.itemText(index) == model_type
