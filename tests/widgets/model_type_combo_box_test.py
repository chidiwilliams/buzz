from buzz.widgets.model_type_combo_box import ModelTypeComboBox


class TestModelTypeComboBox:
    def test_should_display_items(self, qtbot):
        widget = ModelTypeComboBox()
        qtbot.add_widget(widget)

        assert widget.count() == 5
        assert widget.itemText(0) == "Whisper"
        assert widget.itemText(1) == "Whisper.cpp"
        assert widget.itemText(2) == "Hugging Face"
        assert widget.itemText(3) == "Faster Whisper"
        assert widget.itemText(4) == "OpenAI Whisper API"
