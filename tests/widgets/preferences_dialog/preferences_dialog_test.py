import os

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QTabWidget
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.preferences_dialog.preferences_dialog import PreferencesDialog


class TestPreferencesDialog:
    locale_file_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../buzz/locale/lv_LV/LC_MESSAGES/buzz.mo")
    )

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

    def test_create_localized(self, qtbot: QtBot, shortcuts, mocker):
        mocker.patch(
            "PyQt6.QtCore.QLocale.name",
            return_value='lv_LV',
        )

        # Reload the module after the patch
        from importlib import reload
        import buzz.locale
        import buzz.widgets.preferences_dialog.models.preferences
        import buzz.widgets.preferences_dialog.preferences_dialog

        reload(buzz.locale)
        reload(buzz.widgets.preferences_dialog.models.preferences)
        reload(buzz.widgets.preferences_dialog.preferences_dialog)

        from buzz.locale import _
        from buzz.widgets.preferences_dialog.models.preferences import Preferences
        from buzz.widgets.preferences_dialog.preferences_dialog import PreferencesDialog

        dialog = PreferencesDialog(
            shortcuts=shortcuts, preferences=Preferences.load(QSettings())
        )
        qtbot.add_widget(dialog)

        assert os.path.isfile(self.locale_file_path), "File .mo file does not exist"
        assert _("Preferences") == "Iestatījumi"
        assert dialog.windowTitle() == "Iestatījumi"

        tab_widget = dialog.findChild(QTabWidget)
        assert isinstance(tab_widget, QTabWidget)
        assert tab_widget.count() == 4
        assert tab_widget.tabText(0) == "Vispārīgi"
        assert tab_widget.tabText(1) == "Modeļi"
        assert tab_widget.tabText(2) == "Īsinājumi"
        assert tab_widget.tabText(3) == "Mapes vērošana"
