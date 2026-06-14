import logging
from typing import Optional

from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QInputDialog,
    QMessageBox,
    QProgressDialog,
)

from buzz.locale import _
from buzz.plugins.post_processing import FnRunnable


class PluginsDialog(QDialog):
    """Management screen for installing, ordering and configuring plugins."""

    def __init__(self, plugin_manager, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.plugin_manager = plugin_manager
        self._progress: Optional[QProgressDialog] = None

        self.setWindowTitle(_("Plugins"))
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self.resize(840, 480)

        layout = QVBoxLayout(self)

        warning = QLabel(
            _(
                "Plugins run with full access to your system. Only install "
                "plugins from sources you trust."
            )
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        body = QHBoxLayout()

        self.list_widget = QListWidget(self)
        # Wrap long descriptions across multiple lines instead of showing a
        # horizontal scroll bar.
        self.list_widget.setWordWrap(True)
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list_widget.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.list_widget.itemChanged.connect(self.on_item_changed)
        self.list_widget.currentRowChanged.connect(self.update_buttons)
        body.addWidget(self.list_widget, 1)

        buttons_column = QVBoxLayout()

        self.add_button = QPushButton(_("Add by URL..."))
        self.add_button.clicked.connect(self.on_add_clicked)

        self.settings_button = QPushButton(_("Settings..."))
        self.settings_button.clicked.connect(self.on_settings_clicked)

        self.up_button = QPushButton(_("Move Up"))
        self.up_button.clicked.connect(lambda: self.on_move(-1))

        self.down_button = QPushButton(_("Move Down"))
        self.down_button.clicked.connect(lambda: self.on_move(1))

        self.remove_button = QPushButton(_("Remove"))
        self.remove_button.clicked.connect(self.on_remove_clicked)

        for button in (
            self.add_button,
            self.settings_button,
            self.up_button,
            self.down_button,
            self.remove_button,
        ):
            buttons_column.addWidget(button)
        buttons_column.addStretch()

        body.addLayout(buttons_column)
        layout.addLayout(body)

        self.refresh()

    def refresh(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for plugin in self.plugin_manager.all_plugins_in_order():
            meta = plugin.metadata
            text = meta.name
            if meta.description:
                text += f"\n{meta.description}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, meta.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if self.plugin_manager.is_enabled(meta.id)
                else Qt.CheckState.Unchecked
            )
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        self.update_buttons()

    def _current_plugin_id(self) -> Optional[str]:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def update_buttons(self, *args):
        plugin_id = self._current_plugin_id()
        has_selection = plugin_id is not None
        self.settings_button.setEnabled(has_selection)
        self.remove_button.setEnabled(has_selection)

        order = self.plugin_manager.order
        index = order.index(plugin_id) if plugin_id in order else -1
        self.up_button.setEnabled(index > 0)
        self.down_button.setEnabled(0 <= index < len(order) - 1)

    def on_item_changed(self, item: QListWidgetItem):
        plugin_id = item.data(Qt.ItemDataRole.UserRole)
        enabled = item.checkState() == Qt.CheckState.Checked
        self.plugin_manager.set_enabled(plugin_id, enabled)

    def on_move(self, direction: int):
        plugin_id = self._current_plugin_id()
        if plugin_id is None:
            return
        self.plugin_manager.move(plugin_id, direction)
        self.refresh()
        # Reselect the moved plugin.
        for row in range(self.list_widget.count()):
            if self.list_widget.item(row).data(Qt.ItemDataRole.UserRole) == plugin_id:
                self.list_widget.setCurrentRow(row)
                break

    def on_settings_clicked(self):
        plugin_id = self._current_plugin_id()
        if plugin_id is None:
            return
        from buzz.widgets.plugins_dialog.plugin_settings_dialog import (
            PluginSettingsDialog,
        )

        dialog = PluginSettingsDialog(self.plugin_manager, plugin_id, self)
        dialog.exec()

    def on_remove_clicked(self):
        plugin_id = self._current_plugin_id()
        if plugin_id is None:
            return
        confirm = QMessageBox.question(
            self,
            _("Remove plugin"),
            _("Remove plugin '{}'?").format(plugin_id),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.plugin_manager.remove(plugin_id)
        self.refresh()

    def on_add_clicked(self):
        url, ok = QInputDialog.getText(
            self, _("Add plugin"), _("Plugin URL (.zip):")
        )
        if not ok or not url.strip():
            return
        url = url.strip()

        self._progress = QProgressDialog(
            _("Installing plugin..."), "", 0, 0, self
        )
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setCancelButton(None)
        self._progress.show()

        runnable = FnRunnable(lambda: self.plugin_manager.add_from_url(url))
        runnable.signals.finished.connect(self.on_add_finished)
        runnable.signals.error.connect(self.on_add_error)
        QThreadPool.globalInstance().start(runnable)

    def on_add_finished(self):
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        self.refresh()

    def on_add_error(self, error: str):
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        logging.error("Failed to add plugin: %s", error)
        QMessageBox.warning(
            self,
            _("Add plugin failed"),
            _("Could not install the plugin:\n{}").format(error),
        )
