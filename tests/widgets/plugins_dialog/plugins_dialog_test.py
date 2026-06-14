from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import QDialog, QMessageBox, QStyleOptionViewItem

from buzz.plugins.base import PluginMetadata
from buzz.widgets.plugins_dialog.plugins_dialog import PluginsDialog


class _FakePlugin:
    def __init__(self, pid, name, description=""):
        self.metadata = PluginMetadata(id=pid, name=name, description=description)


class _FakeManager:
    def __init__(self, plugins):
        self._plugins = {p.metadata.id: p for p in plugins}
        self.order = [p.metadata.id for p in plugins]
        self.enabled = {pid: True for pid in self.order}
        self.removed = []
        self.set_enabled_calls = []
        self.moved = []
        self.added_urls = []

    def all_plugins_in_order(self):
        return [self._plugins[pid] for pid in self.order]

    def is_enabled(self, pid):
        return self.enabled.get(pid, False)

    def set_enabled(self, pid, value):
        self.enabled[pid] = value
        self.set_enabled_calls.append((pid, value))

    def move(self, pid, direction):
        i = self.order.index(pid)
        j = i + direction
        if 0 <= j < len(self.order):
            self.order[i], self.order[j] = self.order[j], self.order[i]
        self.moved.append((pid, direction))

    def remove(self, pid):
        self.removed.append(pid)
        self.order.remove(pid)
        del self._plugins[pid]

    def add_from_url(self, url):
        self.added_urls.append(url)


@pytest.fixture()
def manager():
    return _FakeManager(
        [
            _FakePlugin("a", "Alpha", "first"),
            _FakePlugin("b", "Beta"),
            _FakePlugin("c", "Gamma"),
        ]
    )


class TestRefresh:
    def test_populates_list_with_check_states(self, qtbot, manager):
        manager.enabled["b"] = False
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)

        assert dialog.list_widget.count() == 3
        item_b = dialog.list_widget.item(1)
        assert item_b.data(Qt.ItemDataRole.UserRole) == "b"
        assert item_b.checkState() == Qt.CheckState.Unchecked
        assert dialog.list_widget.item(0).checkState() == Qt.CheckState.Checked


class TestUpdateButtons:
    def test_no_selection_disables_buttons(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(-1)
        dialog.update_buttons()

        assert dialog.settings_button.isEnabled() is False
        assert dialog.remove_button.isEnabled() is False
        assert dialog.up_button.isEnabled() is False
        assert dialog.down_button.isEnabled() is False

    def test_first_row_cannot_move_up(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(0)

        assert dialog.up_button.isEnabled() is False
        assert dialog.down_button.isEnabled() is True
        assert dialog.settings_button.isEnabled() is True

    def test_last_row_cannot_move_down(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(2)

        assert dialog.up_button.isEnabled() is True
        assert dialog.down_button.isEnabled() is False


class TestItemChanged:
    def test_unchecking_disables_plugin(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)

        dialog.list_widget.item(0).setCheckState(Qt.CheckState.Unchecked)

        assert ("a", False) in manager.set_enabled_calls


class TestMove:
    def test_move_down_reorders_and_reselects(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(0)

        dialog.on_move(1)

        assert manager.moved == [("a", 1)]
        assert manager.order == ["b", "a", "c"]
        # The moved plugin stays selected at its new row.
        assert dialog._current_plugin_id() == "a"

    def test_move_without_selection_is_noop(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(-1)

        dialog.on_move(1)
        assert manager.moved == []


class TestRemove:
    def test_confirm_removes_plugin(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(1)

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            dialog.on_remove_clicked()

        assert manager.removed == ["b"]
        assert dialog.list_widget.count() == 2

    def test_decline_keeps_plugin(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(1)

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ):
            dialog.on_remove_clicked()

        assert manager.removed == []
        assert dialog.list_widget.count() == 3


class TestAddFlow:
    def test_add_cancelled_does_nothing(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)

        with patch(
            "buzz.widgets.plugins_dialog.plugins_dialog.QInputDialog.exec",
            return_value=QDialog.DialogCode.Rejected,
        ):
            dialog.on_add_clicked()

        assert dialog._progress is None

    def test_add_accepted_starts_install(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)

        with patch(
            "buzz.widgets.plugins_dialog.plugins_dialog.QInputDialog.exec",
            return_value=QDialog.DialogCode.Accepted,
        ), patch(
            "buzz.widgets.plugins_dialog.plugins_dialog.QInputDialog.textValue",
            return_value="http://example.com/p.zip",
        ), patch(
            "buzz.widgets.plugins_dialog.plugins_dialog.QThreadPool"
        ) as mock_pool:
            dialog.on_add_clicked()

            mock_pool.globalInstance.return_value.start.assert_called_once()
            assert dialog._progress is not None

    def test_add_finished_closes_progress_and_refreshes(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        manager.order = ["a"]  # change underlying data

        dialog.on_add_finished()

        assert dialog._progress is None
        assert dialog.list_widget.count() == 1

    def test_add_error_shows_warning(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)

        with patch.object(QMessageBox, "warning") as warning:
            dialog.on_add_error("boom")

        warning.assert_called_once()
        assert dialog._progress is None


class TestSettingsClicked:
    def test_opens_settings_dialog_for_selection(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(0)

        with patch(
            "buzz.widgets.plugins_dialog.plugin_settings_dialog.PluginSettingsDialog"
        ) as MockSettings:
            dialog.on_settings_clicked()

        MockSettings.assert_called_once_with(manager, "a", dialog)
        MockSettings.return_value.exec.assert_called_once()

    def test_no_selection_does_not_open_dialog(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)
        dialog.list_widget.setCurrentRow(-1)

        with patch(
            "buzz.widgets.plugins_dialog.plugin_settings_dialog.PluginSettingsDialog"
        ) as MockSettings:
            dialog.on_settings_clicked()

        MockSettings.assert_not_called()


class TestHtmlItemDelegate:
    def test_paint_and_size_hint(self, qtbot, manager):
        dialog = PluginsDialog(manager)
        qtbot.add_widget(dialog)

        delegate = dialog.list_widget.itemDelegate()
        index = dialog.list_widget.model().index(0, 0)

        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 200, 40)

        pixmap = QPixmap(200, 40)
        painter = QPainter(pixmap)
        try:
            delegate.paint(painter, option, index)
        finally:
            painter.end()

        size = delegate.sizeHint(option, index)
        assert size.height() > 0
