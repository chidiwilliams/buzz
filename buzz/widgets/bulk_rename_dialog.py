"""
buzz/widgets/bulk_rename_dialog.py

PyQt6 dialog for the Bulk Audio Renamer feature.

Workflow
--------
1. Pick a folder of audio files.
2. Choose a Buzz model (Whisper, Whisper.cpp, Faster-Whisper, HuggingFace).
3. Tweak trim seconds, word count, language.
4. Click "Preview" — runs transcription in a worker thread; the table fills
   with proposed names as each file completes.
5. Inspect / inline-edit any proposed name.
6. Click "Apply" to commit. An undo log is saved to the source folder.
7. "Undo last" reverses the most recent batch.

The dialog is intentionally separate from the main transcription pipeline
because the *output* is a renamed file on disk, not a transcript file. We
reuse the same WhisperFileTranscriber under the hood so all of Buzz's
existing offline backends work, but we never enqueue tasks on the main
queue worker.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QBrush, QColor, QPalette
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from buzz.locale import _
from buzz.model_loader import ModelDownloader, ModelType, TranscriptionModel
from buzz.transcriber.bulk_renamer import (
    BulkRenamer,
    RenamePlan,
    RenamerConfig,
    apply_plan,
    first_n_words,
    sanitize_filename,
    undo_from_log,
)
from buzz.transcriber.transcriber import LANGUAGES, Task, TranscriptionOptions
from buzz.widgets.model_type_combo_box import ModelTypeComboBox


STATUS_ICON = {
    "pending": "·",
    "ready": "✓",
    "skipped": "—",
    "error": "✗",
    "applied": "★",
}

ROW_COLORS = {
    "ready":   QColor("#e9f6e8"),
    "applied": QColor("#d8eafd"),
    "error":   QColor("#fde6e6"),
    "skipped": QColor("#f4f4f4"),
    "nochange": QColor("#fafafa"),
}


# ---------------------------------------------------------------------------
# Worker thread that drives BulkRenamer (so the dialog stays responsive)
# ---------------------------------------------------------------------------

class _RenameWorker(QThread):
    """Run BulkRenamer.plan_renames in a background thread."""

    progress = pyqtSignal(int, int, object)
    log = pyqtSignal(str, str)
    finished_with_plans = pyqtSignal(list)

    def __init__(self, renamer: BulkRenamer, directory: Path,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._renamer = renamer
        self._directory = directory
        # Pipe BulkRenamer's signals out through our own so the dialog
        # connects in one place.
        renamer.progress.connect(self.progress)
        renamer.log.connect(self.log)
        renamer.finished.connect(self.finished_with_plans)

    def run(self) -> None:  # type: ignore[override]
        self._renamer.plan_renames(self._directory)

    def cancel(self) -> None:
        self._renamer.cancel()


# ---------------------------------------------------------------------------
# The dialog
# ---------------------------------------------------------------------------

class BulkRenameDialog(QDialog):
    """The main rename dialog."""

    COL_STATUS = 0
    COL_ORIGINAL = 1
    COL_PROPOSED = 2
    COL_TRANSCRIPT = 3
    COL_COUNT = 4

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent, flags=Qt.WindowType.Window)
        self.setWindowTitle(_("Rename Audio Files (Whisper)"))
        self.resize(1100, 760)

        self._plans: List[RenamePlan] = []
        self._worker: Optional[_RenameWorker] = None
        self._renamer: Optional[BulkRenamer] = None
        self._model_loader: Optional[ModelDownloader] = None

        self._build_ui()
        self._update_buttons()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        # ---- Configuration form ----
        form = QFormLayout()

        # Folder picker
        self.folder_edit = QLineEdit()
        self.folder_btn = QPushButton(_("Browse…"))
        self.folder_btn.clicked.connect(self._on_pick_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(self.folder_btn)
        folder_widget = QWidget()
        folder_widget.setLayout(folder_row)
        form.addRow(_("Audio folder:"), folder_widget)

        # Model type & size — reuse Buzz's combo box
        self.model_type_combo = ModelTypeComboBox()
        # Use a sensible default if available; otherwise the combo's first item
        try:
            self.model_type_combo.setCurrentText(ModelType.WHISPER_CPP.value)
        except Exception:  # noqa: BLE001 — fall back to whatever's first
            pass
        form.addRow(_("Model type:"), self.model_type_combo)

        # Language (free-form to match Buzz; empty == auto-detect)
        self.language_combo = QComboBox()
        self.language_combo.addItem(_("Detect language"), "")
        for code, label in sorted(LANGUAGES.items(), key=lambda kv: kv[1]):
            self.language_combo.addItem(f"{label} ({code})", code)
        # Default to English for our use case
        en_idx = self.language_combo.findData("en")
        if en_idx >= 0:
            self.language_combo.setCurrentIndex(en_idx)
        form.addRow(_("Language:"), self.language_combo)

        # Knobs row
        knobs = QHBoxLayout()
        knobs.addWidget(QLabel(_("Trim seconds:")))
        self.trim_spin = QDoubleSpinBox()
        self.trim_spin.setRange(1.0, 30.0)
        self.trim_spin.setSingleStep(0.5)
        self.trim_spin.setValue(5.0)
        knobs.addWidget(self.trim_spin)
        knobs.addSpacing(12)
        knobs.addWidget(QLabel(_("Words:")))
        self.words_spin = QSpinBox()
        self.words_spin.setRange(1, 20)
        self.words_spin.setValue(6)
        knobs.addWidget(self.words_spin)
        knobs.addSpacing(12)
        knobs.addWidget(QLabel(_("Max length:")))
        self.maxlen_spin = QSpinBox()
        self.maxlen_spin.setRange(10, 200)
        self.maxlen_spin.setValue(50)
        knobs.addWidget(self.maxlen_spin)
        knobs.addSpacing(12)
        self.keep_prefix_chk = QCheckBox(_("Keep numeric prefix (NN_)"))
        knobs.addWidget(self.keep_prefix_chk)
        knobs.addStretch(1)
        knobs_widget = QWidget()
        knobs_widget.setLayout(knobs)
        form.addRow(_("Options:"), knobs_widget)

        outer.addLayout(form)

        # ---- Action buttons ----
        action_row = QHBoxLayout()
        self.preview_btn = QPushButton(_("Preview Renames"))
        self.preview_btn.clicked.connect(self._on_preview)
        self.cancel_btn = QPushButton(_("Cancel"))
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.apply_btn = QPushButton(_("Apply Renames"))
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        self.undo_btn = QPushButton(_("Undo Last Batch"))
        self.undo_btn.clicked.connect(self._on_undo)
        action_row.addWidget(self.preview_btn)
        action_row.addWidget(self.cancel_btn)
        action_row.addSpacing(12)
        action_row.addWidget(self.apply_btn)
        action_row.addWidget(self.undo_btn)
        action_row.addStretch(1)
        self.close_btn = QPushButton(_("Close"))
        self.close_btn.clicked.connect(self.reject)
        action_row.addWidget(self.close_btn)
        outer.addLayout(action_row)

        # ---- Progress bar ----
        prog_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_label = QLabel(_("Ready"))
        prog_row.addWidget(self.progress_bar, 1)
        prog_row.addWidget(self.progress_label)
        outer.addLayout(prog_row)

        # ---- Plans table ----
        self.table = QTableWidget(0, self.COL_COUNT)
        self.table.setHorizontalHeaderLabels([
            "", _("Original"), _("Proposed (editable)"), _("Transcript snippet"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            self.COL_TRANSCRIPT, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(self.COL_STATUS, 30)
        self.table.setColumnWidth(self.COL_ORIGINAL, 240)
        self.table.setColumnWidth(self.COL_PROPOSED, 320)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        outer.addWidget(self.table, 3)

        # ---- Log pane ----
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(110)
        outer.addWidget(self.log_view, 1)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _log(self, msg: str, level: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        color = {"info": "#222", "warn": "#a60", "error": "#c00"}.get(level, "#222")
        self.log_view.append(
            f'<span style="color:#888">[{ts}]</span> '
            f'<span style="color:{color}">{msg}</span>'
        )

    def _update_buttons(self) -> None:
        running = self._worker is not None and self._worker.isRunning()
        any_changes = any(p.will_change for p in self._plans)
        self.preview_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.apply_btn.setEnabled(not running and any_changes)
        self.undo_btn.setEnabled(not running)

    def _on_pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self,
            _("Choose audio folder"),
            self.folder_edit.text() or os.path.expanduser("~"),
        )
        if d:
            self.folder_edit.setText(d)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _on_preview(self) -> None:
        folder = Path(self.folder_edit.text().strip())
        if not folder.is_dir():
            QMessageBox.critical(self, _("Invalid folder"),
                                 _("Please choose a valid folder."))
            return

        # Build a TranscriptionOptions matching the user's choices.
        model_type = self.model_type_combo.currentData()
        if model_type is None:
            # Older Buzz versions store the value in currentText()
            try:
                model_type = ModelType(self.model_type_combo.currentText())
            except ValueError:
                QMessageBox.critical(self, _("Model error"),
                                     _("Please select a valid model type."))
                return

        # We keep the model size simple for now — the user can pick a
        # specific size in the main preferences dialog and it'll be picked up
        # by `TranscriptionModel`'s defaults. Power users wanting a different
        # size can change it in Buzz's Preferences and reopen this dialog.
        model = TranscriptionModel(model_type=model_type)
        language = self.language_combo.currentData() or None

        transcription_options = TranscriptionOptions(
            language=language,
            task=Task.TRANSCRIBE,
            model=model,
            word_level_timings=False,
            extract_speech=False,
        )

        # Resolve / download the model first. We use ModelDownloader the same
        # way the main file_transcriber widget does.
        self._log(_("Resolving model…"), "info")
        self.preview_btn.setEnabled(False)

        self._model_loader = ModelDownloader(model=model)
        self._model_loader.signals.finished.connect(
            lambda model_path: self._start_preview(folder, transcription_options, model_path)
        )
        self._model_loader.signals.error.connect(self._on_model_error)
        self._model_loader.signals.progress.connect(self._on_model_progress)
        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(self._model_loader)

    def _on_model_progress(self, progress: tuple) -> None:
        # progress is (current, total) bytes
        try:
            current, total = progress
            if total:
                self.progress_label.setText(
                    _("Downloading model: %(pct)d%%") % {"pct": int(100 * current / total)}
                )
        except Exception:
            pass

    def _on_model_error(self, message: str) -> None:
        self._log(_("Model load failed: %s") % message, "error")
        self.progress_label.setText(_("Error"))
        self._update_buttons()

    def _start_preview(self, folder: Path,
                       transcription_options: TranscriptionOptions,
                       model_path: str) -> None:
        cfg = RenamerConfig(
            transcription_options=transcription_options,
            model_path=model_path,
            trim_seconds=self.trim_spin.value(),
            first_words=self.words_spin.value(),
            max_filename_len=self.maxlen_spin.value(),
            keep_numeric_prefix=self.keep_prefix_chk.isChecked(),
        )

        self._plans = []
        self.table.setRowCount(0)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_label.setText(_("Starting…"))
        self._log(_("Previewing renames in %s") % folder, "info")

        self._renamer = BulkRenamer(cfg)
        self._worker = _RenameWorker(self._renamer, folder, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._log)
        self._worker.finished_with_plans.connect(self._on_preview_done)
        self._worker.start()
        self._update_buttons()

    def _on_cancel(self) -> None:
        if self._worker is not None:
            self._log(_("Cancellation requested…"), "warn")
            self._worker.cancel()

    @pyqtSlot(int, int, object)
    def _on_progress(self, done: int, total: int, plan: RenamePlan) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_label.setText(f"{done}/{total}")

    @pyqtSlot(list)
    def _on_preview_done(self, plans: list) -> None:
        self._plans = plans
        self._populate_table()
        self.progress_label.setText(_("Done — %d file(s)") % len(plans))
        if self._worker is not None:
            self._worker.wait()
            self._worker = None
        self._renamer = None
        self._update_buttons()

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------
    def _populate_table(self) -> None:
        # Disable signals while we populate so itemChanged doesn't fire
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for plan in self._plans:
            self._append_row(plan)
        self.table.blockSignals(False)

    def _append_row(self, plan: RenamePlan) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        proposed_display = (
            plan.proposed_path.name if plan.proposed_path else _("(no change)")
        )
        is_no_change = (plan.status == "ready" and not plan.will_change)
        if is_no_change:
            proposed_display = _("(already correct)")

        items = [
            QTableWidgetItem(STATUS_ICON.get(plan.status, "?")),
            QTableWidgetItem(plan.original_path.name),
            QTableWidgetItem(proposed_display),
            QTableWidgetItem(self._snippet(plan.transcript)),
        ]

        # Status column is fixed-width centered text
        items[self.COL_STATUS].setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        # Only the Proposed column is editable
        items[self.COL_STATUS].setFlags(Qt.ItemFlag.ItemIsEnabled)
        items[self.COL_ORIGINAL].setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        items[self.COL_TRANSCRIPT].setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        proposed_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if plan.status == "ready" and not is_no_change:
            proposed_flags |= Qt.ItemFlag.ItemIsEditable
        items[self.COL_PROPOSED].setFlags(proposed_flags)

        # Stash the plan reference on the original-column item so we can
        # find it again from itemChanged callbacks.
        items[self.COL_ORIGINAL].setData(Qt.ItemDataRole.UserRole, id(plan))

        # Row color tag
        color = ROW_COLORS.get("nochange" if is_no_change else plan.status)
        if color is not None:
            for it in items:
                it.setBackground(QBrush(color))
                if is_no_change:
                    it.setForeground(QBrush(QColor("#888")))

        for col, item in enumerate(items):
            self.table.setItem(row, col, item)

    @staticmethod
    def _snippet(text: str) -> str:
        return (text[:200] + "…") if len(text) > 200 else text

    def _plan_for_row(self, row: int) -> Optional[RenamePlan]:
        it = self.table.item(row, self.COL_ORIGINAL)
        if it is None:
            return None
        plan_id = it.data(Qt.ItemDataRole.UserRole)
        for p in self._plans:
            if id(p) == plan_id:
                return p
        return None

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != self.COL_PROPOSED:
            return
        plan = self._plan_for_row(item.row())
        if plan is None or plan.status not in ("ready",):
            return
        new_text = item.text().strip()
        # Allow user to type a stem with or without extension; strip extension.
        stem = Path(new_text).stem if "." in new_text else new_text
        if not stem:
            return
        plan.proposed_name = stem
        plan.proposed_path = plan.original_path.with_name(
            stem + plan.original_path.suffix
        )
        # Re-show the full filename in the cell (keeps display consistent)
        self.table.blockSignals(True)
        item.setText(plan.proposed_path.name)
        self.table.blockSignals(False)
        self._update_buttons()

    def _on_context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        plan = self._plan_for_row(row)
        if plan is None:
            return
        menu = QMenu(self)
        edit_act = menu.addAction(_("Edit proposed name…"))
        skip_act = menu.addAction(_("Skip (don't rename)"))
        reset_act = menu.addAction(_("Reset to AI suggestion"))
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == edit_act:
            self.table.editItem(self.table.item(row, self.COL_PROPOSED))
        elif action == skip_act:
            plan.status = "skipped"
            plan.error = "user skipped"
            self._populate_table()
            self._update_buttons()
        elif action == reset_act and plan.transcript:
            stem = sanitize_filename(
                first_n_words(plan.transcript, self.words_spin.value()),
                self.maxlen_spin.value(),
            )
            plan.proposed_name = stem
            plan.proposed_path = plan.original_path.with_name(
                stem + plan.original_path.suffix
            )
            plan.status = "ready"
            self._populate_table()
            self._update_buttons()

    # ------------------------------------------------------------------
    # Apply / Undo
    # ------------------------------------------------------------------
    def _on_apply(self) -> None:
        n = sum(1 for p in self._plans if p.will_change)
        if n == 0:
            QMessageBox.information(self, _("Nothing to do"),
                                    _("There are no changes to apply."))
            return
        ok = QMessageBox.question(
            self, _("Confirm"),
            _("Apply %d rename(s)? An undo log will be saved alongside the audio files.") % n,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return

        folder = Path(self.folder_edit.text().strip())
        log_path = folder / f".undo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        summary = apply_plan(self._plans, log_path)
        self._populate_table()
        self._log(
            _("Applied %(applied)d, skipped %(skipped)d, errors %(errors)d.") % {
                "applied": summary["applied_count"],
                "skipped": summary["skipped_count"],
                "errors": summary["error_count"],
            },
            "info",
        )
        msg = _("Renamed %d file(s).") % summary["applied_count"]
        if summary["applied_count"]:
            msg += "\n\n" + _("Undo log: %s") % log_path.name
        QMessageBox.information(self, _("Done"), msg)
        self._update_buttons()

    def _on_undo(self) -> None:
        folder = Path(self.folder_edit.text().strip())
        if not folder.is_dir():
            QMessageBox.critical(self, _("Invalid folder"),
                                 _("Please choose a valid folder."))
            return
        logs = sorted(folder.glob(".undo_*.json"), reverse=True)
        if not logs:
            path, _flt = QFileDialog.getOpenFileName(
                self,
                _("Pick undo log"),
                str(folder),
                "Undo logs (.undo_*.json)",
            )
            if not path:
                return
            log_path = Path(path)
        else:
            log_path = logs[0]
        ok = QMessageBox.question(
            self, _("Undo"),
            _("Reverse the renames in %s?") % log_path.name,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            res = undo_from_log(log_path)
        except OSError as e:
            QMessageBox.critical(self, _("Undo failed"), str(e))
            return
        self._log(
            _("Reverted %(rev)d, failed %(fail)d.") % {
                "rev": res["reverted_count"], "fail": res["failed_count"]},
            "warn" if res["failed"] else "info",
        )
        QMessageBox.information(
            self, _("Undo complete"),
            _("Reverted %d file(s).") % res["reverted_count"],
        )

    # ------------------------------------------------------------------
    def closeEvent(self, event):  # noqa: N802 — Qt naming
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        super().closeEvent(event)
