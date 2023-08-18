from buzz.widgets.openai_api_key_line_edit import OpenAIAPIKeyLineEdit


class TestOpenAIAPIKeyLineEdit:
    def test_should_emit_key_changed(self, qtbot):
        line_edit = OpenAIAPIKeyLineEdit(key="")
        qtbot.add_widget(line_edit)

        with qtbot.wait_signal(line_edit.key_changed):
            line_edit.setText("abcdefg")

    def test_should_toggle_visibility(self, qtbot):
        line_edit = OpenAIAPIKeyLineEdit(key="")
        qtbot.add_widget(line_edit)

        assert line_edit.echoMode() == OpenAIAPIKeyLineEdit.EchoMode.Password

        toggle_action = line_edit.actions()[0]

        toggle_action.trigger()
        assert line_edit.echoMode() == OpenAIAPIKeyLineEdit.EchoMode.Normal

        toggle_action.trigger()
        assert line_edit.echoMode() == OpenAIAPIKeyLineEdit.EchoMode.Password
