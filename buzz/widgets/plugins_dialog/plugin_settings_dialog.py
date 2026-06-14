from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QCheckBox,
    QPlainTextEdit,
    QDialogButtonBox,
    QLabel,
)

from buzz.locale import _
from buzz.plugins.base import ConfigFieldType
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.password_line_edit import PasswordLineEdit


class PluginSettingsDialog(QDialog):
    """Settings editor for a single plugin, generated from its config schema."""

    def __init__(
        self,
        plugin_manager,
        plugin_id: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.plugin_manager = plugin_manager
        self.plugin_id = plugin_id
        self.plugin = plugin_manager.plugins.get(plugin_id)
        self._editors = {}

        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        if self.plugin is None:
            layout.addWidget(QLabel(_("Plugin not available.")))
            return

        self.setWindowTitle(self.plugin.metadata.name)

        if self.plugin.metadata.description:
            description = QLabel(self.plugin.metadata.description)
            description.setWordWrap(True)
            layout.addWidget(description)

        form = QFormLayout()
        values = plugin_manager.get_config(plugin_id)

        for field in self.plugin.metadata.config_fields:
            value = values.get(field.key, field.default)
            editor = self._create_editor(field, value)
            self._editors[field.key] = (field, editor)
            label = QLabel(field.label or field.key)
            # Show the field's description as a tooltip on both the label and
            # the input, since it is the only place the description surfaces.
            if field.description:
                label.setToolTip(field.description)
                editor.setToolTip(field.description)
            form.addRow(label, editor)

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(_("Ok"))
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(_("Cancel"))
        button_box.accepted.connect(self.on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_editor(self, field, value):
        if field.type == ConfigFieldType.BOOL:
            checkbox = QCheckBox(self)
            checkbox.setChecked(_coerce_bool(value))
            return checkbox
        if field.type == ConfigFieldType.TEXTAREA:
            editor = QPlainTextEdit(self)
            editor.setPlainText(str(value) if value is not None else "")
            editor.setMinimumHeight(100)
            return editor
        if field.type == ConfigFieldType.PASSWORD:
            return PasswordLineEdit(
                str(value) if value is not None else "",
                field.placeholder,
                self,
            )
        editor = LineEdit(str(value) if value is not None else "", self)
        if field.placeholder:
            editor.setPlaceholderText(field.placeholder)
        return editor

    def _editor_value(self, field, editor):
        if field.type == ConfigFieldType.BOOL:
            return editor.isChecked()
        if field.type == ConfigFieldType.TEXTAREA:
            return editor.toPlainText()
        return editor.text()

    def on_accept(self):
        values = {
            key: self._editor_value(field, editor)
            for key, (field, editor) in self._editors.items()
        }
        self.plugin_manager.set_config(self.plugin_id, values)
        self.accept()


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
