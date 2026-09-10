from dataclasses import replace
import threading
import uuid
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from buzz.meeting.meeting_notes import MeetingNotesService, NotesError
from buzz.meeting.meeting_summary import (
    meeting_summary_to_json,
    MeetingSummaryFreshness as F,
)
from buzz.meeting.openai_compatible_provider import OpenAICompatibleProviderConfig
from buzz.widgets.meeting_notes_controller import MeetingNotesController
from buzz.widgets.meeting_notes_panel import MeetingNotesPanel, ManualResponseDialog
from buzz.widgets.meeting_notes_configuration import (
    NotesConfiguration,
    NotesConfigurationDialog,
    secret_name,
)
from tests.meeting.meeting_notes_test import Repository, summary, deterministic_clock
from tests.widgets.meeting_detail_widget_test import DetailService, snapshot, MEETING_ID


@pytest.fixture(scope="session")
def qapp_cls():
    return QApplication


class ControlledProvider:
    def __init__(self):
        self.entered = threading.Event()
        self.allow_result = threading.Event()
        self.cleanup_entered = threading.Event()
        self.allow_cleanup = threading.Event()
        self.calls = []
        self.result = summary()
        self.error = None

    def summarize(self, request):
        self.calls.append(("summarize", threading.get_ident()))
        self.entered.set()
        assert self.allow_result.wait(15), "Test did not release provider"
        if self.error:
            raise self.error
        return self.result

    def shutdown(self):
        self.calls.append(("shutdown", threading.get_ident()))
        self.cleanup_entered.set()
        return self.allow_cleanup.is_set()

    @property
    def cleanup_required(self):
        return not self.allow_cleanup.is_set()


@pytest.fixture
def controller(qtbot, monkeypatch):
    deterministic_clock(monkeypatch)
    provider = ControlledProvider()
    service = MeetingNotesService(DetailService(snapshot()), Repository())
    control = MeetingNotesController(service, provider_factory=lambda config: provider)
    yield control, provider
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy, timeout=15000)
    control.close()


def config():
    return OpenAICompatibleProviderConfig(
        "https://example.invalid/v1", "model", "SECRET_SENTINEL"
    )


@pytest.fixture
def panel(controller, qtbot):
    control, _ = controller
    result = MeetingNotesPanel(control, Mock())
    qtbot.addWidget(result)
    result.open_meeting(MEETING_ID)
    return result


def test_worker_thread_save_owner_and_cleanup_retention(controller, qtbot, monkeypatch):
    control, provider = controller
    owner = threading.get_ident()
    save_threads = []
    original = control.service.save
    monkeypatch.setattr(
        control.service,
        "save",
        lambda candidate: (
            save_threads.append(threading.get_ident()),
            original(candidate),
        )[1],
    )
    control.submit(MEETING_ID, config())
    qtbot.waitUntil(provider.entered.is_set)
    assert control.busy
    worker, thread, operation = (
        control.worker,
        control.worker_thread,
        control.operation_id,
    )
    assert worker.thread() is thread and thread is not QThread.currentThread()
    with pytest.raises(NotesError):
        control.submit(MEETING_ID, config())
    assert not control.close()
    provider.allow_result.set()
    qtbot.waitUntil(lambda: len(control.service.repository.items) == 1)
    qtbot.waitUntil(provider.cleanup_entered.is_set)
    assert save_threads == [owner]
    assert control.worker is worker and control.worker_thread is thread
    assert control.worker.provider is provider and control.operation_id == operation
    assert not control.close()
    with pytest.raises(NotesError):
        control.submit(MEETING_ID, config())
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy)
    assert control.close() and control.worker is None and control.worker_thread is None
    assert all(tid != owner for _, tid in provider.calls)
    assert len({tid for _, tid in provider.calls}) == 1
    assert [name for name, _ in provider.calls].count("summarize") == 1
    with pytest.raises(NotesError):
        control.submit(MEETING_ID, config())


def test_manual_no_provider_secret_or_network_shared_save(controller, monkeypatch):
    control, provider = controller
    monkeypatch.setattr(
        control,
        "provider_factory",
        Mock(side_effect=AssertionError("Manual cannot call provider")),
    )
    for name in ("get_secret", "set_secret", "delete_secret"):
        monkeypatch.setattr(
            f"buzz.store.keyring_store.{name}",
            Mock(side_effect=AssertionError("Manual cannot access secrets")),
        )
    save = Mock(wraps=control.service.save)
    monkeypatch.setattr(control.service, "save", save)
    with pytest.raises(NotesError):
        control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    assert "phrase one" in control.copy_request(MEETING_ID)
    with pytest.raises(Exception):
        control.import_response(MEETING_ID, "invalid")
    save.assert_not_called()
    artifact = control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    save.assert_called_once()
    assert artifact == control.service.repository.items[0]
    assert not provider.calls


def test_api_shared_save_and_db_retry_same_uuid(controller, qtbot, monkeypatch):
    control, provider = controller
    save = Mock(wraps=control.service.save)
    monkeypatch.setattr(control.service, "save", save)
    control.service.repository.failure = RuntimeError("db error")
    control.submit(MEETING_ID, config())
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy)
    assert len(control.candidates) == 1 and not control.service.repository.items
    candidate = control.candidates[MEETING_ID]
    control.service.repository.failure = None
    control.retry_save(MEETING_ID)
    assert save.call_count == 2
    assert save.call_args_list[0].args[0] is save.call_args_list[1].args[0] is candidate


def test_source_changed_while_provider_pending(controller, qtbot):
    control, provider = controller
    messages = []
    control.status.connect(lambda mid, message: messages.append(message))
    control.submit(MEETING_ID, config())
    qtbot.waitUntil(provider.entered.is_set)
    control.service.detail = DetailService(RuntimeError("read unavailable"))
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy)
    assert not control.service.repository.attempts
    assert any("Source changed" in m for m in messages)


@pytest.mark.parametrize("raw_result", [False, True])
def test_worker_sanitizes_failure_no_mutations(controller, qtbot, caplog, raw_result):
    control, provider = controller
    if raw_result:
        provider.result = "SECRET_SENTINEL raw response"
    else:
        provider.error = RuntimeError("SECRET_SENTINEL header raw response")
    messages = []
    control.status.connect(lambda mid, message: messages.append(message))
    control.submit(MEETING_ID, config())
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy)
    assert not control.service.repository.attempts
    assert "SECRET_SENTINEL" not in caplog.text + repr(messages) + repr(config())
    assert sum(name == "summarize" for name, _ in provider.calls) == 1


def test_history_newest_default_preserves_explicit_then_selects_created(
    controller, panel
):
    control, _ = controller
    control.copy_request(MEETING_ID)
    first = control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    second = control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    panel.selected_id = None
    panel.refresh()
    assert panel.history.itemData(0) == panel.selected_id == second.summary_id
    panel.history.setCurrentIndex(1)
    panel.refresh()
    assert panel.selected_id == first.summary_id
    third = control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    assert panel.selected_id == third.summary_id
    assert "None recorded" in panel.content.toPlainText()
    assert "Profile version" in panel.provenance.text()


def test_history_failure_is_not_empty(controller, panel, monkeypatch):
    control, _ = controller
    monkeypatch.setattr(
        control.service.repository,
        "list_for_meeting",
        Mock(side_effect=ValueError("corrupt")),
    )
    panel.refresh()
    assert "History could not be loaded" in panel.message.text()
    assert not panel.history.isEnabled()
    assert not panel.actions["Export Minutes"].isEnabled()


@pytest.mark.parametrize("closed", [False, True])
def test_navigation_or_closed_panel_not_mutated_by_late_result(
    controller, panel, qtbot, closed
):
    control, provider = controller
    control.submit(MEETING_ID, config())
    qtbot.waitUntil(provider.entered.is_set)
    if closed:
        panel.closed = True
    else:
        panel.open_meeting(uuid.uuid4())
    text, selected, status = (
        panel.content.toPlainText(),
        panel.selected_id,
        panel.message.text(),
    )
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy)
    assert control.service.repository.items[0].meeting_id == MEETING_ID
    assert (panel.content.toPlainText(), panel.selected_id, panel.message.text()) == (
        text,
        selected,
        status,
    )


def test_manual_dialog_preserves_input_and_requires_explicit_repair(controller, qtbot):
    control, _ = controller
    control.copy_request(MEETING_ID)
    dialog = ManualResponseDialog(control, MEETING_ID)
    qtbot.addWidget(dialog)
    text = "```json\n" + meeting_summary_to_json(summary()) + "\n```"
    dialog.input.setPlainText(text)
    assert not dialog.repair.isEnabled()
    dialog.process(False)
    assert dialog.input.toPlainText() == text
    assert dialog.repair.isEnabled() and not control.service.repository.items
    dialog.process(True)
    assert len(control.service.repository.items) == 1


def test_export_cancel_no_summary_and_exact_selected(
    controller, panel, monkeypatch, tmp_path
):
    control, _ = controller
    picker = Mock(return_value=("", ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", picker)
    panel.export()
    picker.assert_not_called()
    control.copy_request(MEETING_ID)
    first = control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    control.import_response(
        MEETING_ID, meeting_summary_to_json(replace(summary(), summary="newer"))
    )
    panel.history.setCurrentIndex(1)
    panel.export()
    assert not list(tmp_path.iterdir())
    export = Mock(wraps=control.export)
    monkeypatch.setattr(control, "export", export)
    path = tmp_path / "minutes.txt"
    picker.return_value = (str(path), "Text (*.txt)")
    panel.export()
    assert export.call_args.args[1] == first.summary_id
    assert "We discussed the plan" in path.read_text()


@pytest.mark.parametrize("freshness", [F.STALE, F.INDETERMINATE, None])
def test_export_ui_requires_ack_before_dialog(
    controller, panel, monkeypatch, freshness
):
    control, _ = controller
    control.copy_request(MEETING_ID)
    control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    monkeypatch.setattr(control, "freshness", lambda _: freshness)
    picker = Mock()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", picker)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
    )
    panel.export()
    picker.assert_not_called()


def test_extension_resolution_and_final_path_overwrite(
    controller, panel, monkeypatch, tmp_path
):
    control, _ = controller
    control.copy_request(MEETING_ID)
    control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    final = tmp_path / "minutes.txt"
    final.write_text("existing")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(tmp_path / "minutes.md"), "Text (*.txt)"),
    )
    questions = []

    def answer(parent, title, message):
        questions.append((title, message))
        return (
            QMessageBox.StandardButton.Yes
            if len(questions) == 1
            else QMessageBox.StandardButton.No
        )

    monkeypatch.setattr(QMessageBox, "question", answer)
    panel.export()
    assert final.read_text() == "existing"
    assert len(questions) == 2 and str(final) in questions[1][1]


def test_endpoint_secrets_never_in_settings(qtbot):
    from buzz.settings.settings import Settings

    settings = Settings("notes-test")
    secrets = {}
    operations = NotesConfiguration(
        settings,
        get=lambda name: secrets.get(name, ""),
        set=lambda name, value: secrets.__setitem__(name, value),
        delete=lambda name: secrets.pop(name, None),
    )
    a, b = "https://a.invalid/v1", "https://b.invalid/v1"
    operations.save(a, "model", 5.0, "SECRET_SENTINEL_A")
    operations.save(b, "model", 5.0, "SECRET_SENTINEL_B")
    assert secret_name(a) != secret_name(b)
    assert "SECRET_SENTINEL" not in repr(
        [settings.settings.value(key) for key in settings.settings.allKeys()]
    )
    dialog = NotesConfigurationDialog(operations)
    qtbot.addWidget(dialog)
    assert dialog.key.text() == "SECRET_SENTINEL_B"
    dialog.endpoint.setText(a)
    assert dialog.key.text() == "SECRET_SENTINEL_A"
    dialog.endpoint.setText("https://new.invalid/v1")
    assert dialog.key.text() == ""
    operations.save(a, "model", 5.0, "")
    assert operations.provider_config().api_key is None


def test_string_keyring_failures_never_log_secrets(monkeypatch, caplog):
    from buzz.store import keyring_store

    monkeypatch.setattr(keyring_store, "_is_linux", lambda: False)
    for name in ("get_password", "delete_password"):
        monkeypatch.setattr(
            keyring_store.keyring,
            name,
            Mock(side_effect=RuntimeError("SECRET_SENTINEL")),
        )
    assert keyring_store.get_secret("test") == ""
    keyring_store.delete_secret("test")
    assert "SECRET_SENTINEL" not in caplog.text
    assert "Unable to" in caplog.text


def test_real_qsql_save_stays_on_owner_thread(controller, qtbot, db):
    from buzz.db.meeting_storage_repository import QSqlMeetingRepository
    from buzz.db.meeting_transcription_repository import (
        QSqlMeetingTranscriptionRepository,
    )
    from buzz.db.meeting_summary_repository import QSqlMeetingSummaryRepository
    from tests.db.meeting_summary_repository_test import (
        _insert_meeting,
        _insert_generation,
    )

    control, provider = controller
    generation_id = control.prepare(MEETING_ID).generation_id
    _insert_meeting(QSqlMeetingRepository(db), str(MEETING_ID))
    _insert_generation(
        QSqlMeetingTranscriptionRepository(db), str(MEETING_ID), str(generation_id)
    )
    owner, calls = threading.get_ident(), []

    class CheckedRepository(QSqlMeetingSummaryRepository):
        def save(self, artifact):
            calls.append(threading.get_ident())
            assert threading.get_ident() == owner
            super().save(artifact)

    control.service.repository = CheckedRepository(db)
    control.submit(MEETING_ID, config())
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy)
    assert calls == [owner]
    assert len(control.history(MEETING_ID)) == 1


def test_confirmed_close_waits_for_persistence_and_verified_thread_completion(
    controller, qtbot, monkeypatch, qapp
):
    from buzz.widgets.main_window import MainWindow
    from buzz.db.service.transcription_service import TranscriptionService

    control, provider = controller
    monkeypatch.setattr(
        "buzz.widgets.main_window.PluginManager.initialize", lambda _: None
    )
    database_closed = Mock()
    monkeypatch.setattr(qapp, "close_database", database_closed, raising=False)
    window = MainWindow(
        Mock(spec=TranscriptionService),
        Mock(),
        control.service.detail,
        Mock(),
        Mock(),
        meeting_notes=control,
    )
    qtbot.addWidget(window)
    window.show()
    window.on_meeting_open_requested(MEETING_ID)
    panel = window.meeting_detail_widget.notes_panel
    before = panel.content.toPlainText()
    control.submit(MEETING_ID, config())
    qtbot.waitUntil(provider.entered.is_set)
    assert not window.close()
    assert control.closing and window.isVisible()
    database_closed.assert_not_called()
    provider.allow_result.set()
    qtbot.waitUntil(lambda: len(control.service.repository.items) == 1)
    qtbot.waitUntil(provider.cleanup_entered.is_set)
    assert not window.close()
    database_closed.assert_not_called()
    assert panel.content.toPlainText() == before
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not window.isVisible())
    database_closed.assert_called_once()
    assert control.worker_thread is None
    assert len(control.service.repository.items) == 1


def test_cancelled_active_meeting_close_does_not_start_ai_shutdown(
    controller, qtbot, monkeypatch
):
    from PyQt6.QtCore import QObject, pyqtSignal
    from buzz.widgets.main_window import MainWindow
    from buzz.db.service.transcription_service import TranscriptionService

    class ActiveMeeting(QObject):
        saved = pyqtSignal(object)
        released = pyqtSignal()
        active = True

    control, _ = controller
    monkeypatch.setattr(
        "buzz.widgets.main_window.PluginManager.initialize", lambda _: None
    )
    active = ActiveMeeting()
    window = MainWindow(
        Mock(spec=TranscriptionService),
        Mock(),
        Mock(),
        Mock(),
        Mock(),
        meeting_controller=active,
        meeting_notes=control,
    )
    qtbot.addWidget(window)
    window.meeting_capture_widget = Mock()
    window.meeting_capture_widget.confirm_end.return_value = False
    window.show()
    assert not window.close()
    assert not control.closing and not window._meeting_close_pending
    active.active = False
    window.close()


def test_quit_event_still_routes_through_window_close(qapp):
    from types import SimpleNamespace
    from PyQt6.QtCore import QEvent
    from buzz.widgets.application import Application

    close = Mock(return_value=False)
    owner = SimpleNamespace(window=SimpleNamespace(close=close))
    assert Application.event(owner, QEvent(QEvent.Type.Quit)) is True
    close.assert_called_once_with()


def test_worker_waits_for_owner_acknowledgement_before_cleanup(qapp):
    from buzz.widgets.meeting_notes_controller import NotesWorker
    from buzz.meeting.meeting_notes import assemble

    provider = ControlledProvider()
    provider.allow_result.set()
    provider.allow_cleanup.set()
    worker = NotesWorker(
        uuid.uuid4(), assemble(snapshot()), config(), lambda _: provider
    )
    outcomes = []
    worker.outcome.connect(lambda *args: outcomes.append(args))
    worker.run()
    assert len(outcomes) == 1
    assert [name for name, _ in provider.calls] == ["summarize"]
    worker.cleanup()
    assert [name for name, _ in provider.calls] == ["summarize", "shutdown"]


def test_new_meeting_history_read_failure_cannot_display_previous_meeting(
    controller, panel, monkeypatch
):
    control, _ = controller
    control.copy_request(MEETING_ID)
    control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    assert "We discussed" in panel.content.toPlainText()
    monkeypatch.setattr(control, "history", Mock(side_effect=ValueError("corrupt")))
    panel.open_meeting(uuid.uuid4())
    assert panel.content.toPlainText() == ""
    assert panel.selected_id is None
    assert "History could not be loaded" in panel.message.text()


def test_close_retains_unsaved_candidate_for_explicit_retry(controller, qtbot):
    control, provider = controller
    control.service.repository.failure = RuntimeError("DB unavailable")
    control.submit(MEETING_ID, config())
    assert not control.close()
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy)
    candidate = control.candidates[MEETING_ID]
    assert not control.close()
    control.service.repository.failure = None
    control.retry_save(MEETING_ID)
    assert control.service.repository.items == [candidate.artifact]
    assert control.close()


def test_equal_creation_times_use_repository_tie_order_but_select_new_result(
    controller, panel, monkeypatch
):
    from datetime import datetime, timezone

    control, _ = controller
    original = control.service.candidate
    ids = iter((uuid.UUID(int=20), uuid.UUID(int=10)))

    def candidate(context, result):
        value = original(context, result)
        return replace(
            value,
            artifact=replace(
                value.artifact,
                summary_id=next(ids),
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )

    monkeypatch.setattr(control.service, "candidate", candidate)
    control.copy_request(MEETING_ID)
    first = control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    second = control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    assert panel.selected_id == second.summary_id
    panel.selected_id = None
    panel.refresh()
    assert (
        panel.selected_id
        == first.summary_id
        == control.history(MEETING_ID)[-1].summary_id
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        (F.FRESH, "FRESH"),
        (F.STALE, "STALE"),
        (F.INDETERMINATE, "INDETERMINATE"),
        (None, "Cannot verify freshness"),
    ],
)
def test_panel_presents_exact_freshness_state(
    controller, panel, monkeypatch, value, expected
):
    control, _ = controller
    control.copy_request(MEETING_ID)
    control.import_response(MEETING_ID, meeting_summary_to_json(summary()))
    monkeypatch.setattr(control, "freshness", lambda _: value)
    panel.refresh()
    assert panel.provenance.text().splitlines()[0].endswith(" | " + expected)


def test_actual_detail_close_blocks_late_presentation_update(controller, qtbot):
    from buzz.widgets.meeting_detail_widget import MeetingDetailWidget

    control, provider = controller
    detail = MeetingDetailWidget(
        control.service.detail, Mock(), Mock(), meeting_notes=control
    )
    qtbot.addWidget(detail)
    detail.open_meeting(MEETING_ID)
    detail.show()
    control.submit(MEETING_ID, config())
    qtbot.waitUntil(provider.entered.is_set)
    assert detail.close()
    before = detail.notes_panel.content.toPlainText()
    provider.allow_result.set()
    provider.allow_cleanup.set()
    qtbot.waitUntil(lambda: not control.busy)
    assert len(control.service.repository.items) == 1
    assert detail.notes_panel.content.toPlainText() == before
    assert detail.notes_panel.selected_id is None


def test_clipboard_failure_does_not_prepare_import_or_relabel_old_request(
    controller, panel, monkeypatch
):
    control, _ = controller
    clipboard = Mock()
    clipboard.text.return_value = ""
    monkeypatch.setattr(QApplication, "clipboard", lambda: clipboard)
    panel.copy()
    assert MEETING_ID not in control.manual_contexts
    assert not panel.actions["Import AI Response"].isEnabled()
    assert "Could not copy" in panel.message.text()
    original = control.copy_request(MEETING_ID)
    context = control.manual_contexts[MEETING_ID]
    source = snapshot()
    control.service.detail = DetailService(
        replace(
            source,
            transcript=replace(
                source.transcript,
                segments=(replace(source.transcript.segments[0], text="new source"),),
            ),
        )
    )
    panel.copy()
    assert control.manual_contexts[MEETING_ID] is context
    assert "phrase one" in original
