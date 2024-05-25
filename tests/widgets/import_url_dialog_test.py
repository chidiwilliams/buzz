from unittest.mock import patch

from buzz.locale import _
from buzz.widgets.import_url_dialog import ImportURLDialog


class TestImportURLDialog:
    def test_should_show_error_with_invalid_url(self, qtbot):
        dialog = ImportURLDialog()
        dialog.line_edit.setText("bad-url")

        with patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical:
            dialog.button_box.button(dialog.button_box.StandardButton.Ok).click()
            mock_critical.assert_called_with(
                dialog, _("Invalid URL"), _("The URL you entered is invalid.")
            )

    def test_should_return_url_with_valid_url(self, qtbot):
        dialog = ImportURLDialog()
        dialog.line_edit.setText("https://example.com")

        dialog.button_box.button(dialog.button_box.StandardButton.Ok).click()
        assert dialog.url == "https://example.com"
