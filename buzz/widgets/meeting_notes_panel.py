"""Meeting Detail AI Notes presentation and local round-trip/export dialogs."""
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QPlainTextEdit,
    QDialog,
    QFileDialog,
    QMessageBox,
)
from buzz.meeting.meeting_notes import MANUAL_RESPONSE_MAX_CHARS, SourceChangedError
from buzz.meeting.meeting_summary import MeetingSummaryFreshness
from buzz.widgets.meeting_notes_configuration import NotesConfigurationDialog


def freshness_text(value):
    return "Cannot verify freshness" if value is None else value.value


def summary_text(artifact):
    summary = artifact.summary
    sections = [summary.title or "AI Notes", summary.summary]
    collections = (
        ("Participants", [p.name or "Unknown" for p in summary.participants]),
        (
            "Topics",
            [t.title + (f": {t.summary}" if t.summary else "") for t in summary.topics],
        ),
        ("Decisions", [d.text for d in summary.decisions]),
        (
            "Action items",
            [
                f"{a.task} — Owner: {a.owner or 'Unknown'}; Due: {a.due_date or 'Unknown'}"
                for a in summary.action_items
            ],
        ),
        ("Open questions", [q.text for q in summary.open_questions]),
        ("Risks", [r.text for r in summary.risks]),
    )
    for label, values in collections:
        sections.append(
            label + "\n" + ("\n".join(values) if values else "None recorded")
        )
    return "\n\n".join(sections)


class ManualResponseDialog(QDialog):
    def __init__(self, controller, meeting_id, parent=None):
        super().__init__(parent)
        self.controller, self.meeting_id = controller, meeting_id
        self.setWindowTitle("Import AI Response")
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        self.message = QLabel(
            f"Paste the response to your copied request. Limit: {MANUAL_RESPONSE_MAX_CHARS:,} characters.",
            self,
        )
        self.message.setWordWrap(True)
        self.input = QPlainTextEdit(self)
        self.strict = QPushButton("Import AI Response", self)
        self.repair = QPushButton("Try Safe Formatting Repair", self)
        self.repair.setEnabled(False)
        self.strict.clicked.connect(lambda: self.process(False))
        self.repair.clicked.connect(lambda: self.process(True))
        self.input.textChanged.connect(self.input_changed)
        for widget in (self.message, self.input, self.strict, self.repair):
            layout.addWidget(widget)

    def input_changed(self):
        self.repair.setEnabled(False)
        self.strict.setEnabled(
            self.input.document().characterCount() - 1 <= MANUAL_RESPONSE_MAX_CHARS
        )
        if not self.strict.isEnabled():
            self.message.setText(
                "Response exceeds the 65,536 character limit. Shorten it before importing."
            )

    def process(self, repair):
        try:
            self.controller.import_response(
                self.meeting_id, self.input.toPlainText(), repair=repair
            )
        except SourceChangedError:
            self.message.setText(
                "Source changed. Close this dialog and copy a new AI Request."
            )
            self.strict.setEnabled(False)
            self.repair.setEnabled(False)
        except Exception:
            if self.meeting_id in self.controller.candidates:
                self.message.setText(
                    "Validated response could not be saved. Close this dialog and use Retry Save."
                )
                self.strict.setEnabled(False)
                self.repair.setEnabled(False)
            else:
                self.message.setText(
                    "Response failed validation. Input is preserved. You may explicitly try safe formatting repair."
                )
                self.repair.setEnabled(
                    not repair
                    and len(self.input.toPlainText()) <= MANUAL_RESPONSE_MAX_CHARS
                )
            self.controller.changed.emit(self.meeting_id, None)
        else:
            self.accept()


class MeetingNotesPanel(QWidget):
    def __init__(self, controller, configuration, parent=None):
        super().__init__(parent)
        self.controller, self.configuration = controller, configuration
        self.meeting_id = None
        self.selected_id = None
        self.artifacts = {}
        self.closed = False
        layout = QVBoxLayout(self)
        self.history = QComboBox(self)
        self.history.currentIndexChanged.connect(self.select)
        self.provenance = QLabel(self)
        self.provenance.setWordWrap(True)
        self.content = QPlainTextEdit(self)
        self.content.setReadOnly(True)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        self.source = QLabel(self)
        self.source.setWordWrap(True)
        self.actions = {}
        buttons = QGridLayout()
        for name, callback in (
            ("Copy AI Request", self.copy),
            ("Import AI Response", self.import_response),
            ("Generate with API", self.generate),
            ("API Configuration", self.configure),
            ("Export Minutes", self.export),
            ("Retry Save", self.retry_save),
            ("Discard Pending Save", self.discard_save),
        ):
            button = QPushButton(name, self)
            button.clicked.connect(callback)
            index = len(self.actions)
            buttons.addWidget(button, index // 4, index % 4)
            self.actions[name] = button
        for widget in (
            self.history,
            self.provenance,
            self.content,
            self.source,
            self.message,
        ):
            layout.addWidget(widget)
        layout.addLayout(buttons)
        controller.changed.connect(self.changed)
        controller.status.connect(self.status)
        self.refresh()

    def open_meeting(self, meeting_id):
        if self.meeting_id != meeting_id:
            self.selected_id = None
            self.artifacts = {}
            self.history.blockSignals(True)
            self.history.clear()
            self.history.blockSignals(False)
            self.content.clear()
            self.provenance.clear()
            self.message.clear()
        self.meeting_id = meeting_id
        self.closed = False
        self.refresh()

    def changed(self, meeting_id, selected_id):
        if self.closed or self.controller.closing:
            return
        if meeting_id == self.meeting_id:
            if selected_id is not None:
                self.selected_id = selected_id
            self.refresh()
        else:
            # Only the global busy button changes; never redirect content.
            self.actions["Generate with API"].setEnabled(
                False
                if self.controller.busy
                else self.actions["Copy AI Request"].isEnabled()
            )

    def status(self, meeting_id, message):
        if (
            not self.closed
            and not self.controller.closing
            and meeting_id == self.meeting_id
        ):
            self.message.setText(message)

    def refresh(self):
        for button in self.actions.values():
            button.setEnabled(False)
        self.actions["API Configuration"].setEnabled(True)
        if self.meeting_id is None or self.closed:
            return
        try:
            context = self.controller.prepare(self.meeting_id)
            self.source.setText(
                "Uses current reviewed speaker names."
                if context.review_id
                else "Uses final transcript only. No fresh readable speaker review participates."
            )
            ready = True
        except Exception:
            self.source.setText(
                "A complete readable final transcript is required. Check final transcription status or retry it."
            )
            ready = False
        pending = self.meeting_id in self.controller.candidates
        self.actions["Copy AI Request"].setEnabled(ready and not pending)
        self.actions["Import AI Response"].setEnabled(
            ready and not pending and self.meeting_id in self.controller.manual_contexts
        )
        self.actions["Generate with API"].setEnabled(
            ready
            and not pending
            and not self.controller.busy
            and not self.controller.closing
        )
        self.actions["Retry Save"].setEnabled(pending)
        self.actions["Discard Pending Save"].setEnabled(pending)
        try:
            history = self.controller.history(self.meeting_id)
        except Exception:
            self.message.setText(
                "History could not be loaded. Stored summary data may be unreadable."
            )
            self.provenance.setText("Cannot verify freshness")
            self.history.setEnabled(False)
            return
        self.history.setEnabled(True)
        self.artifacts = {a.summary_id: a for a in history}
        if self.selected_id not in self.artifacts:
            self.selected_id = history[-1].summary_id if history else None
        self.history.blockSignals(True)
        self.history.clear()
        for artifact in reversed(history):
            self.history.addItem(
                f"{artifact.created_at.astimezone():%Y-%m-%d %H:%M:%S} — {artifact.summary.title or 'AI Notes'}",
                artifact.summary_id,
            )
        self.history.setCurrentIndex(self.history.findData(self.selected_id))
        self.history.blockSignals(False)
        self.render_selected()

    def select(self):
        self.selected_id = self.history.currentData()
        self.render_selected()

    def render_selected(self):
        artifact = self.artifacts.get(self.selected_id)
        self.actions["Export Minutes"].setEnabled(artifact is not None)
        if artifact is None:
            self.provenance.clear()
            self.content.setPlainText(
                "No AI Notes yet. Copy an AI Request and import its response, or configure an API and generate notes."
            )
            return
        self.content.setPlainText(summary_text(artifact))
        self.provenance.setText(
            f"Created: {artifact.created_at.astimezone().isoformat()} | {freshness_text(self.controller.freshness(artifact))}\n"
            f"Source generation: {artifact.source_generation_id} | Profile version: {artifact.source_profile_version}\n"
            f"Review ID: {artifact.source_review_id or 'None'} | Revision: {artifact.source_review_revision if artifact.source_review_revision is not None else 'None'}\n"
            f"Schema version: {artifact.summary.schema_version} | Prompt version: {artifact.summary.prompt_version}"
        )

    def copy(self):
        try:
            self.controller.copy_request(self.meeting_id, copy=self._copy_to_clipboard)
            self.message.setText(
                "AI Request copied. Import the response to this exact request."
            )
        except Exception:
            self.message.setText(
                "Could not copy AI Request. Check final transcription status and try copying again."
            )
        self.refresh()

    @staticmethod
    def _copy_to_clipboard(text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        if clipboard.text() != text:
            raise RuntimeError("Clipboard did not retain the AI request.")

    def import_response(self):
        if self.meeting_id not in self.controller.manual_contexts:
            return
        ManualResponseDialog(self.controller, self.meeting_id, self).exec()
        self.refresh()

    def configure(self):
        NotesConfigurationDialog(self.configuration, self).exec()

    def generate(self):
        try:
            self.controller.submit(
                self.meeting_id, self.configuration.provider_config()
            )
        except Exception:
            self.message.setText(
                "Could not start API generation. Check configuration and source status, then retry."
            )
        self.refresh()

    def retry_save(self):
        try:
            self.controller.retry_save(self.meeting_id)
            self.message.setText("AI Notes saved.")
        except SourceChangedError:
            self.message.setText(
                "Source changed. Nothing was saved. Prepare a new request."
            )
        except Exception:
            self.message.setText("Save failed. Retry Save retains the same summary.")
        self.refresh()

    def discard_save(self):
        self.controller.discard_save(self.meeting_id)

    def export(self):
        if self.selected_id is None:
            return
        meeting_id, summary_id = self.meeting_id, self.selected_id
        try:
            artifact = self.controller.selected(meeting_id, summary_id)
            freshness = self.controller.freshness(artifact)
            acknowledged = False
            if freshness is not MeetingSummaryFreshness.FRESH:
                acknowledged = (
                    QMessageBox.question(
                        self,
                        "Export older or unverified notes",
                        f"{freshness_text(freshness)}. These notes may not reflect the current transcript or speaker review. Export this selected summary?",
                    )
                    == QMessageBox.StandardButton.Yes
                )
                if not acknowledged:
                    return
            filters = {
                "Markdown (*.md)": ".md",
                "Text (*.txt)": ".txt",
                "DOCX (*.docx)": ".docx",
            }
            name, chosen = QFileDialog.getSaveFileName(
                self,
                "Export Minutes",
                "minutes.md",
                ";;".join(filters),
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if not name:
                return
            path = Path(name)
            suffix = filters.get(chosen, ".md")
            if path.suffix.lower() != suffix:
                resolved = path.with_suffix(suffix)
                if (
                    QMessageBox.question(
                        self,
                        "Resolve file extension",
                        f"Save as {resolved.name} to match the selected format?",
                    )
                    != QMessageBox.StandardButton.Yes
                ):
                    return
                path = resolved
            if (
                path.exists()
                and QMessageBox.question(self, "Overwrite Minutes", f"Replace {path}?")
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.controller.export(
                meeting_id, summary_id, path, acknowledged=acknowledged
            )
            self.message.setText("Minutes exported.")
        except Exception:
            self.message.setText(
                "Minutes export failed. Verify the selected summary, freshness and destination, then retry."
            )
