from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QTabWidget
from pytestqt.qtbot import QtBot

from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.preferences_dialog.preferences_dialog import PreferencesDialog


class TestPreferencesDialog:
    def test_create(self, qtbot: QtBot):
        dialog = PreferencesDialog(
            shortcuts={},
            preferences=Preferences.load(QSettings()),
        )
        qtbot.add_widget(dialog)

        assert dialog.windowTitle() == "Preferences"

        tab_widget = dialog.findChild(QTabWidget)
        assert isinstance(tab_widget, QTabWidget)
        assert tab_widget.count() == 4
        assert tab_widget.tabText(0) == "General"
        assert tab_widget.tabText(1) == "Models"
        assert tab_widget.tabText(2) == "Shortcuts"
        assert tab_widget.tabText(3) == "Folder Watch"
