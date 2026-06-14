from PyQt6.QtWidgets import QLineEdit

from buzz.widgets.password_line_edit import PasswordLineEdit


class TestPasswordLineEdit:
    def test_defaults_to_password_echo_mode(self, qtbot):
        line_edit = PasswordLineEdit()
        qtbot.add_widget(line_edit)
        assert line_edit.echoMode() == QLineEdit.EchoMode.Password

    def test_applies_initial_text_and_placeholder(self, qtbot):
        line_edit = PasswordLineEdit("secret", "Enter key")
        qtbot.add_widget(line_edit)
        assert line_edit.text() == "secret"
        assert line_edit.placeholderText() == "Enter key"

    def test_toggle_reveals_then_hides_text(self, qtbot):
        line_edit = PasswordLineEdit()
        qtbot.add_widget(line_edit)

        line_edit.toggle_show_action.trigger()
        assert line_edit.echoMode() == QLineEdit.EchoMode.Normal

        line_edit.toggle_show_action.trigger()
        assert line_edit.echoMode() == QLineEdit.EchoMode.Password

    def test_toggle_swaps_icon(self, qtbot):
        line_edit = PasswordLineEdit()
        qtbot.add_widget(line_edit)

        before = line_edit.toggle_show_action.icon().cacheKey()
        line_edit.toggle_show_action.trigger()
        after = line_edit.toggle_show_action.icon().cacheKey()
        assert before != after
