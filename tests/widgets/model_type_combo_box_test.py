import sys

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
                ],
                marks=pytest.mark.skipif(
                    sys.platform == "linux", reason="Skip on Linux"
                ),
            ),
            pytest.param(
                ["Whisper.cpp", "OpenAI Whisper API"],
                marks=pytest.mark.skipif(
                    sys.platform != "linux", reason="Skip on non-Linux"
                ),
            ),
        ],
    )
    def test_should_display_items(self, qtbot, model_types):
        widget = ModelTypeComboBox()
        qtbot.add_widget(widget)

        assert widget.count() == len(model_types)
        for index, model_type in enumerate(model_types):
            assert widget.itemText(index) == model_type
