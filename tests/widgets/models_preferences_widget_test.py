from PyQt6.QtWidgets import QComboBox

from buzz.widgets.models_preferences_widget import ModelsPreferencesWidget


class TestModelsPreferencesWidget:
    def test_should_show_model_list(self, qtbot):
        widget = ModelsPreferencesWidget()
        qtbot.add_widget(widget)

        first_item = widget.model_list_widget.topLevelItem(0)
        assert first_item.text(0) == 'Downloaded'

        second_item = widget.model_list_widget.topLevelItem(1)
        assert second_item.text(0) == 'Available for Download'

    def test_should_change_model_type(self, qtbot):
        widget = ModelsPreferencesWidget()
        qtbot.add_widget(widget)

        combo_box = widget.findChild(QComboBox)
        assert isinstance(combo_box, QComboBox)
        combo_box.setCurrentText('Faster Whisper')

        first_item = widget.model_list_widget.topLevelItem(0)
        assert first_item.text(0) == 'Downloaded'

        second_item = widget.model_list_widget.topLevelItem(1)
        assert second_item.text(0) == 'Available for Download'
