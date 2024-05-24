from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QTabWidget
from PyQt6.QtCore import QLocale
from unittest.mock import patch
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.preferences_dialog.preferences_dialog import PreferencesDialog


class TestPreferencesDialog:
    def test_create(self, qtbot: QtBot, shortcuts):
        dialog = PreferencesDialog(
            shortcuts=shortcuts, preferences=Preferences.load(QSettings())
        )
        qtbot.add_widget(dialog)

        assert dialog.windowTitle() == _("Preferences")

        tab_widget = dialog.findChild(QTabWidget)
        assert isinstance(tab_widget, QTabWidget)
        assert tab_widget.count() == 4
        assert tab_widget.tabText(0) == _("General")
        assert tab_widget.tabText(1) == _("Models")
        assert tab_widget.tabText(2) == _("Shortcuts")
        assert tab_widget.tabText(3) == _("Folder Watch")

    def test_create_localized(self, qtbot: QtBot, shortcuts):
        with patch.object(QLocale, 'uiLanguages', return_value=['lv_LV']):
            dialog = PreferencesDialog(
                shortcuts=shortcuts, preferences=Preferences.load(QSettings())
            )
            qtbot.add_widget(dialog)

            assert dialog.windowTitle() == "Iestatījumi"

            tab_widget = dialog.findChild(QTabWidget)
            assert isinstance(tab_widget, QTabWidget)
            assert tab_widget.count() == 4
            assert tab_widget.tabText(0) == "Vispārīgi"
            assert tab_widget.tabText(1) == "Modeļi"
            assert tab_widget.tabText(2) == "Īsinājumi"
            assert tab_widget.tabText(3) == "Mapes vērošana"