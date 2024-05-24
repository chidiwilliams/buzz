import os

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QPushButton
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.model_loader import (
    TranscriptionModel,
    ModelType,
)
from buzz.widgets.preferences_dialog.models_preferences_widget import (
    ModelsPreferencesWidget,
)
from tests.model_loader import get_model_path


class TestModelsPreferencesWidget:
    @pytest.fixture(scope="class")
    def clear_model_cache(self):
        for model_type in ModelType:
            if model_type.is_available():
                path = TranscriptionModel(model_type=model_type).get_local_model_path()
                if path and os.path.isfile(path):
                    os.remove(path)

    def test_should_show_model_list(self, qtbot):
        widget = ModelsPreferencesWidget()
        qtbot.add_widget(widget)

        first_item = widget.model_list_widget.topLevelItem(0)
        assert first_item.text(0) == _("Downloaded")

        second_item = widget.model_list_widget.topLevelItem(1)
        assert second_item.text(0) == _("Available for Download")

    def test_should_change_model_type(self, qtbot):
        widget = ModelsPreferencesWidget()
        qtbot.add_widget(widget)

        combo_box = widget.findChild(QComboBox)
        assert isinstance(combo_box, QComboBox)
        combo_box.setCurrentText("Faster Whisper")

        first_item = widget.model_list_widget.topLevelItem(0)
        assert first_item.text(0) == _("Downloaded")

        second_item = widget.model_list_widget.topLevelItem(1)
        assert second_item.text(0) == _("Available for Download")

    def test_should_download_model(self, qtbot: QtBot, clear_model_cache):
        # make progress dialog non-modal to unblock qtbot.wait_until
        widget = ModelsPreferencesWidget(
            progress_dialog_modality=Qt.WindowModality.NonModal
        )
        qtbot.add_widget(widget)

        assert widget.model.get_local_model_path() is None

        available_item = widget.model_list_widget.topLevelItem(1)
        assert available_item.text(0) == _("Available for Download")

        tiny_item = available_item.child(0)
        assert tiny_item.text(0) == "Tiny"
        tiny_item.setSelected(True)

        download_button = widget.findChild(QPushButton, "DownloadButton")
        assert isinstance(download_button, QPushButton)

        assert download_button.text() == _("Download")
        download_button.click()

        def downloaded_model():
            assert not download_button.isVisible()

            _downloaded_item = widget.model_list_widget.topLevelItem(0)
            assert _downloaded_item.childCount() > 0
            assert _downloaded_item.child(0).text(0) == "Tiny"

            _available_item = widget.model_list_widget.topLevelItem(1)
            assert (
                _available_item.childCount() == 0
                or _available_item.child(0).text(0) != "Tiny"
            )

            assert os.path.isfile(widget.model.get_local_model_path())

        qtbot.wait_until(callback=downloaded_model, timeout=60_000)

    @pytest.fixture(scope="class")
    def default_model_path(self) -> str:
        return get_model_path(transcription_model=(TranscriptionModel.default()))

    def test_should_show_downloaded_model(self, qtbot, default_model_path):
        widget = ModelsPreferencesWidget()
        widget.show()
        qtbot.add_widget(widget)

        available_item = widget.model_list_widget.topLevelItem(0)
        assert available_item.text(0) == _("Downloaded")

        tiny_item = available_item.child(0)
        assert tiny_item.text(0) == "Tiny"
        tiny_item.setSelected(True)

        delete_button = widget.findChild(QPushButton, "DeleteButton")
        assert delete_button.isVisible()

        show_file_location_button = widget.findChild(
            QPushButton, "ShowFileLocationButton"
        )
        assert show_file_location_button.isVisible()
