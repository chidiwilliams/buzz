import html
import logging
from typing import Optional

from PyQt6.QtCore import Qt, QThreadPool, QSize, QRectF
from PyQt6.QtGui import QTextDocument, QAbstractTextDocumentLayout, QPalette
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QProgressDialog,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
    QApplication,
)

from buzz.locale import _
from buzz.plugins.post_processing import FnRunnable


class _HtmlItemDelegate(QStyledItemDelegate):
    """Renders list item text as rich text (HTML) with word wrapping.

    Used so a plugin's name can be bold while its description stays regular,
    while preserving the native check indicator and selection background.
    """

    def _document(self, option: QStyleOptionViewItem, width: int) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(option.text)
        doc.setTextWidth(width)
        return doc

    def paint(self, painter, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)

        style = options.widget.style() if options.widget else QApplication.style()

        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, options, options.widget
        )

        doc = self._document(options, text_rect.width())

        # Let the style paint everything except the text (background, selection,
        # and the check indicator).
        options.text = ""
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, options, painter, options.widget
        )

        # Draw the rich text using the palette's text color so it is visible on
        # both light and dark themes.
        ctx = QAbstractTextDocumentLayout.PaintContext()
        if option.state & QStyle.StateFlag.State_Selected:
            ctx.palette.setColor(
                QPalette.ColorRole.Text,
                option.palette.color(QPalette.ColorRole.HighlightedText),
            )
        else:
            ctx.palette.setColor(
                QPalette.ColorRole.Text,
                option.palette.color(QPalette.ColorRole.Text),
            )

        painter.save()
        painter.translate(text_rect.topLeft())
        painter.setClipRect(QRectF(0, 0, text_rect.width(), text_rect.height()))
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option, index):
        options = QStyleOptionViewItem(option)
        self.initStyleOption(options, index)

        style = options.widget.style() if options.widget else QApplication.style()
        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, options, options.widget
        )
        width = text_rect.width() if text_rect.width() > 0 else options.rect.width()
        doc = self._document(options, width)
        return QSize(int(doc.idealWidth()), int(doc.size().height()) + 8)


class PluginsDialog(QDialog):
    """Management screen for installing, ordering and configuring plugins."""

    def __init__(self, plugin_manager, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.plugin_manager = plugin_manager
        self._progress: Optional[QProgressDialog] = None

        self.setWindowTitle(_("Plugins"))
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self.resize(1000, 640)

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
        self.list_widget.setItemDelegate(_HtmlItemDelegate(self.list_widget))
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
            text = f"<b>{html.escape(meta.name)}</b>"
            if meta.description:
                text += f"<br>{html.escape(meta.description)}"
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
        dialog = QInputDialog(self)
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.setWindowTitle(_("Add plugin"))
        dialog.setLabelText(_("Plugin URL (.zip):"))
        dialog.setOkButtonText(_("Ok"))
        dialog.setCancelButtonText(_("Cancel"))
        # Match the width of the Plugins / Settings dialogs.
        dialog.setMinimumWidth(self.width())
        line_edit = dialog.findChild(QLineEdit)
        if line_edit is not None:
            line_edit.setMinimumWidth(self.width() - 80)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        url = dialog.textValue().strip()
        if not url:
            return

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
