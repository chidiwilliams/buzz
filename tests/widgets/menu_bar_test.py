from PyQt6.QtCore import QSettings

from buzz.settings.settings import Settings
from buzz.settings.shortcut_settings import ShortcutSettings
from buzz.widgets.menu_bar import MenuBar
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.preferences_dialog.preferences_dialog import PreferencesDialog


class TestMenuBar:
    def test_open_preferences_dialog(self, qtbot):
        menu_bar = MenuBar(
            shortcuts=ShortcutSettings(Settings()).load(),
            preferences=Preferences.load(QSettings()),
        )
        qtbot.add_widget(menu_bar)

        preferences_dialog = menu_bar.findChild(PreferencesDialog)
        assert preferences_dialog is None

        menu_bar.preferences_action.trigger()

        preferences_dialog = menu_bar.findChild(PreferencesDialog)
        assert isinstance(preferences_dialog, PreferencesDialog)
