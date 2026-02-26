from unittest.mock import patch, Mock

from PyQt6.QtCore import QSettings

from buzz.widgets.menu_bar import MenuBar
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.preferences_dialog.preferences_dialog import PreferencesDialog


class TestMenuBar:
    def test_import_folder_action_emits_signal(self, qtbot, shortcuts):
        menu_bar = MenuBar(
            shortcuts=shortcuts, preferences=Preferences.load(QSettings())
        )
        qtbot.add_widget(menu_bar)

        signal_mock = Mock()
        menu_bar.import_folder_action_triggered.connect(signal_mock)
        menu_bar.import_folder_action.trigger()

        signal_mock.assert_called_once()

    def test_open_preferences_dialog(self, qtbot, shortcuts):
        menu_bar = MenuBar(
            shortcuts=shortcuts, preferences=Preferences.load(QSettings())
        )
        qtbot.add_widget(menu_bar)

        preferences_dialog = menu_bar.findChild(PreferencesDialog)
        assert preferences_dialog is None

        menu_bar.preferences_action.trigger()

        preferences_dialog = menu_bar.findChild(PreferencesDialog)
        assert isinstance(preferences_dialog, PreferencesDialog)
