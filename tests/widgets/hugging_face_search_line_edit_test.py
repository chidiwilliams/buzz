import json
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt, QEvent, QPoint
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtNetwork import QNetworkReply, QNetworkAccessManager
from PyQt6.QtWidgets import QListWidgetItem
from pytestqt.qtbot import QtBot

from buzz.widgets.transcriber.hugging_face_search_line_edit import HuggingFaceSearchLineEdit


@pytest.fixture
def widget(qtbot: QtBot):
    mock_manager = MagicMock(spec=QNetworkAccessManager)
    mock_manager.finished = MagicMock()
    mock_manager.finished.connect = MagicMock()
    w = HuggingFaceSearchLineEdit(network_access_manager=mock_manager)
    qtbot.add_widget(w)
    # Prevent popup.show() from triggering a Wayland fatal protocol error
    # in headless/CI environments where popup windows lack a transient parent.
    w.popup.show = MagicMock()
    return w


class TestHuggingFaceSearchLineEdit:
    def test_initial_state(self, widget):
        assert widget.text() == ""
        assert widget.placeholderText() != ""

    def test_default_value_set(self, qtbot: QtBot):
        mock_manager = MagicMock(spec=QNetworkAccessManager)
        mock_manager.finished = MagicMock()
        mock_manager.finished.connect = MagicMock()
        w = HuggingFaceSearchLineEdit(default_value="openai/whisper-tiny", network_access_manager=mock_manager)
        qtbot.add_widget(w)
        assert w.text() == "openai/whisper-tiny"

    def test_on_text_edited_emits_model_selected(self, widget, qtbot: QtBot):
        spy = MagicMock()
        widget.model_selected.connect(spy)
        widget.on_text_edited("some/model")
        spy.assert_called_once_with("some/model")

    def test_fetch_models_skips_short_text(self, widget):
        widget.setText("ab")
        result = widget.fetch_models()
        assert result is None

    def test_fetch_models_makes_request_for_long_text(self, widget):
        widget.setText("whisper-tiny")
        mock_reply = MagicMock()
        widget.network_manager.get = MagicMock(return_value=mock_reply)
        result = widget.fetch_models()
        widget.network_manager.get.assert_called_once()
        assert result == mock_reply

    def test_fetch_models_url_contains_search_text(self, widget):
        widget.setText("whisper")
        widget.network_manager.get = MagicMock(return_value=MagicMock())
        widget.fetch_models()
        call_args = widget.network_manager.get.call_args[0][0]
        assert "whisper" in call_args.url().toString()

    def test_on_request_response_network_error_does_not_populate_popup(self, widget):
        mock_reply = MagicMock(spec=QNetworkReply)
        mock_reply.error.return_value = QNetworkReply.NetworkError.ConnectionRefusedError
        widget.on_request_response(mock_reply)
        assert widget.popup.count() == 0

    def test_on_request_response_populates_popup(self, widget):
        mock_reply = MagicMock(spec=QNetworkReply)
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        models = [{"id": "openai/whisper-tiny"}, {"id": "openai/whisper-base"}]
        mock_reply.readAll.return_value.data.return_value = json.dumps(models).encode()
        widget.on_request_response(mock_reply)
        assert widget.popup.count() == 2
        assert widget.popup.item(0).text() == "openai/whisper-tiny"
        assert widget.popup.item(1).text() == "openai/whisper-base"

    def test_on_request_response_empty_models_does_not_show_popup(self, widget):
        mock_reply = MagicMock(spec=QNetworkReply)
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.readAll.return_value.data.return_value = json.dumps([]).encode()
        widget.on_request_response(mock_reply)
        assert widget.popup.count() == 0
        widget.popup.show.assert_not_called()

    def test_on_request_response_item_has_user_role_data(self, widget):
        mock_reply = MagicMock(spec=QNetworkReply)
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        models = [{"id": "facebook/mms-1b-all"}]
        mock_reply.readAll.return_value.data.return_value = json.dumps(models).encode()
        widget.on_request_response(mock_reply)
        item = widget.popup.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == "facebook/mms-1b-all"

    def test_on_select_item_emits_model_selected(self, widget, qtbot: QtBot):
        item = QListWidgetItem("openai/whisper-tiny")
        item.setData(Qt.ItemDataRole.UserRole, "openai/whisper-tiny")
        widget.popup.addItem(item)
        widget.popup.setCurrentItem(item)

        spy = MagicMock()
        widget.model_selected.connect(spy)
        widget.on_select_item()

        spy.assert_called_with("openai/whisper-tiny")
        assert widget.text() == "openai/whisper-tiny"

    def test_on_select_item_hides_popup(self, widget):
        item = QListWidgetItem("openai/whisper-tiny")
        item.setData(Qt.ItemDataRole.UserRole, "openai/whisper-tiny")
        widget.popup.addItem(item)
        widget.popup.setCurrentItem(item)

        with patch.object(widget.popup, 'hide') as mock_hide:
            widget.on_select_item()
        mock_hide.assert_called_once()

    def test_on_popup_selected_stops_timer(self, widget):
        widget.timer.start()
        assert widget.timer.isActive()
        widget.on_popup_selected()
        assert not widget.timer.isActive()

    def test_event_filter_ignores_non_popup_target(self, widget):
        other = MagicMock()
        event = MagicMock()
        assert widget.eventFilter(other, event) is False

    def test_event_filter_mouse_press_hides_popup(self, widget):
        event = MagicMock()
        event.type.return_value = QEvent.Type.MouseButtonPress
        with patch.object(widget.popup, 'hide') as mock_hide:
            result = widget.eventFilter(widget.popup, event)
        assert result is True
        mock_hide.assert_called_once()

    def test_event_filter_escape_hides_popup(self, widget, qtbot: QtBot):
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        with patch.object(widget.popup, 'hide') as mock_hide:
            result = widget.eventFilter(widget.popup, event)
        assert result is True
        mock_hide.assert_called_once()

    def test_event_filter_enter_selects_item(self, widget, qtbot: QtBot):
        item = QListWidgetItem("openai/whisper-tiny")
        item.setData(Qt.ItemDataRole.UserRole, "openai/whisper-tiny")
        widget.popup.addItem(item)
        widget.popup.setCurrentItem(item)

        spy = MagicMock()
        widget.model_selected.connect(spy)

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        result = widget.eventFilter(widget.popup, event)
        assert result is True
        spy.assert_called_with("openai/whisper-tiny")

    def test_event_filter_enter_no_item_returns_true(self, widget, qtbot: QtBot):
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        result = widget.eventFilter(widget.popup, event)
        assert result is True

    def test_event_filter_navigation_keys_return_false(self, widget):
        for key in [Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home,
                    Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown]:
            event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            assert widget.eventFilter(widget.popup, event) is False

    def test_event_filter_other_key_hides_popup(self, widget):
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
        with patch.object(widget.popup, 'hide') as mock_hide:
            widget.eventFilter(widget.popup, event)
        mock_hide.assert_called_once()
