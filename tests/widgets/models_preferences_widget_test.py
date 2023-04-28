from buzz.widgets.models_preferences_widget import ModelsPreferencesWidget


class TestModelsPreferencesWidget:
    def test_should_show_model_list(self, qtbot):
        widget = ModelsPreferencesWidget()
        qtbot.add_widget(widget)
