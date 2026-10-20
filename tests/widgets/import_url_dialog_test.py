from unittest.mock import patch
import pytest

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

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com",
            "https://www.youtube.com/watch?v=AuZoDsNmG_s&t=3s",
        ],
    )
    def test_should_return_url_with_valid_url(self, qtbot, url):
        dialog = ImportURLDialog()
        dialog.line_edit.setText(url)

        dialog.button_box.button(dialog.button_box.StandardButton.Ok).click()
        assert dialog.url == url
