from PyQt6.QtCore import Qt

from buzz.locale import _
from buzz.model_loader import ModelType
from buzz.widgets.model_download_progress_dialog import ModelDownloadProgressDialog


class TestModelDownloadProgressDialog:
    def test_should_show_dialog(self, qtbot):
        dialog = ModelDownloadProgressDialog(model_type=ModelType.WHISPER, parent=None)
        qtbot.add_widget(dialog)
        assert dialog.labelText() == f"{_('Downloading model')} (0%)"

    def test_should_update_label_on_progress(self, qtbot):
        dialog = ModelDownloadProgressDialog(model_type=ModelType.WHISPER, parent=None)
        qtbot.add_widget(dialog)
        dialog.set_value(0.0)

        dialog.set_value(0.01)
        assert dialog.labelText().startswith(f"{_('Downloading model')} (1%")

        dialog.set_value(0.1)
        assert dialog.labelText().startswith(f"{_('Downloading model')} (10%")

    # Other windows should not be processing while models are being downloaded
    def test_should_be_an_application_modal(self, qtbot):
        dialog = ModelDownloadProgressDialog(model_type=ModelType.WHISPER, parent=None)
        qtbot.add_widget(dialog)
        assert dialog.windowModality() == Qt.WindowModality.WindowModal
