from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QCheckBox, QPlainTextEdit

from buzz.plugins.base import ConfigField, ConfigFieldType, PluginMetadata
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.password_line_edit import PasswordLineEdit
from buzz.widgets.plugins_dialog.plugin_settings_dialog import (
    PluginSettingsDialog,
    _coerce_bool,
)


class _FakePlugin:
    def __init__(self, fields):
        self.metadata = PluginMetadata(
            id="my_plugin",
            name="My Plugin",
            description="A demo plugin",
            config_fields=fields,
        )


def _make_manager(fields, config=None):
    plugin = _FakePlugin(fields)
    manager = MagicMock()
    manager.plugins = {"my_plugin": plugin}
    manager.get_config.return_value = config or {}
    return manager


class TestCoerceBool:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (True, True),
            (False, False),
            ("true", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("nope", False),
            (1, True),
            (0, False),
            (None, False),
            ([], False),
            (["x"], True),
        ],
    )
    def test_coerce(self, value, expected):
        assert _coerce_bool(value) is expected


class TestEditorFactory:
    def test_bool_field_creates_checkbox(self, qtbot):
        fields = [ConfigField(key="flag", label="Flag", type=ConfigFieldType.BOOL)]
        manager = _make_manager(fields, {"flag": True})
        dialog = PluginSettingsDialog(manager, "my_plugin")
        qtbot.add_widget(dialog)

        _field, editor = dialog._editors["flag"]
        assert isinstance(editor, QCheckBox)
        assert editor.isChecked() is True

    def test_textarea_field_creates_plain_text_edit(self, qtbot):
        fields = [
            ConfigField(key="body", label="Body", type=ConfigFieldType.TEXTAREA)
        ]
        manager = _make_manager(fields, {"body": "hello"})
        dialog = PluginSettingsDialog(manager, "my_plugin")
        qtbot.add_widget(dialog)

        _field, editor = dialog._editors["body"]
        assert isinstance(editor, QPlainTextEdit)
        assert editor.toPlainText() == "hello"

    def test_password_field_creates_password_line_edit(self, qtbot):
        fields = [
            ConfigField(
                key="key",
                label="Key",
                type=ConfigFieldType.PASSWORD,
                placeholder="sk-...",
            )
        ]
        manager = _make_manager(fields, {"key": "secret"})
        dialog = PluginSettingsDialog(manager, "my_plugin")
        qtbot.add_widget(dialog)

        _field, editor = dialog._editors["key"]
        assert isinstance(editor, PasswordLineEdit)
        assert editor.text() == "secret"

    def test_text_field_creates_line_edit_with_placeholder(self, qtbot):
        fields = [
            ConfigField(key="name", label="Name", placeholder="Your name")
        ]
        manager = _make_manager(fields, {})
        dialog = PluginSettingsDialog(manager, "my_plugin")
        qtbot.add_widget(dialog)

        _field, editor = dialog._editors["name"]
        assert isinstance(editor, LineEdit)
        assert editor.placeholderText() == "Your name"

    def test_uses_default_when_value_missing(self, qtbot):
        fields = [ConfigField(key="name", label="Name", default="fallback")]
        manager = _make_manager(fields, {})
        dialog = PluginSettingsDialog(manager, "my_plugin")
        qtbot.add_widget(dialog)

        _field, editor = dialog._editors["name"]
        assert editor.text() == "fallback"

    def test_description_sets_tooltip(self, qtbot):
        fields = [
            ConfigField(key="name", label="Name", description="Your full name")
        ]
        manager = _make_manager(fields, {})
        dialog = PluginSettingsDialog(manager, "my_plugin")
        qtbot.add_widget(dialog)

        _field, editor = dialog._editors["name"]
        assert editor.toolTip() == "Your full name"


class TestUnavailablePlugin:
    def test_missing_plugin_shows_message(self, qtbot):
        manager = MagicMock()
        manager.plugins = {}
        dialog = PluginSettingsDialog(manager, "missing")
        qtbot.add_widget(dialog)
        assert dialog._editors == {}


class TestOnAccept:
    def test_collects_and_saves_values(self, qtbot):
        fields = [
            ConfigField(key="name", label="Name"),
            ConfigField(key="flag", label="Flag", type=ConfigFieldType.BOOL),
            ConfigField(key="body", label="Body", type=ConfigFieldType.TEXTAREA),
        ]
        manager = _make_manager(
            fields, {"name": "a", "flag": False, "body": "b"}
        )
        dialog = PluginSettingsDialog(manager, "my_plugin")
        qtbot.add_widget(dialog)

        dialog._editors["name"][1].setText("new name")
        dialog._editors["flag"][1].setChecked(True)
        dialog._editors["body"][1].setPlainText("new body")

        dialog.on_accept()

        manager.set_config.assert_called_once_with(
            "my_plugin",
            {"name": "new name", "flag": True, "body": "new body"},
        )
