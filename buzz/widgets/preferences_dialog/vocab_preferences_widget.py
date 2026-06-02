import json
import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QMessageBox,
    QLabel,
    QHeaderView,
    QAbstractItemView,
)

from buzz.locale import _
from buzz.vocab_replacement import load_vocab, save_vocab


class VocabPreferencesWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        description = QLabel(_("Define word replacements to correct transcription errors. "
                               "After transcription, each 'Wrong' text will be replaced with the 'Correct' text."))
        description.setWordWrap(True)
        layout.addWidget(description)

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels([_("Wrong (original)"), _("Correct (replacement)")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()

        self.add_button = QPushButton(_("Add Row"))
        self.add_button.clicked.connect(self.on_add_row)
        button_row.addWidget(self.add_button)

        self.remove_button = QPushButton(_("Remove Selected"))
        self.remove_button.clicked.connect(self.on_remove_selected)
        button_row.addWidget(self.remove_button)

        button_row.addStretch()

        self.import_button = QPushButton(_("Import JSON"))
        self.import_button.clicked.connect(self.on_import)
        button_row.addWidget(self.import_button)

        self.export_button = QPushButton(_("Export JSON"))
        self.export_button.clicked.connect(self.on_export)
        button_row.addWidget(self.export_button)

        self.save_button = QPushButton(_("Save"))
        self.save_button.clicked.connect(self.on_save)
        button_row.addWidget(self.save_button)

        layout.addLayout(button_row)
        self.setLayout(layout)

        self._load_from_disk()

    def _load_from_disk(self):
        vocab = load_vocab()
        self.table.setRowCount(0)
        for wrong, correct in vocab.items():
            self._add_row(wrong, correct)

    def _add_row(self, wrong: str = "", correct: str = ""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(wrong))
        self.table.setItem(row, 1, QTableWidgetItem(correct))

    def _collect_vocab(self) -> dict[str, str]:
        vocab: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            wrong_item = self.table.item(row, 0)
            correct_item = self.table.item(row, 1)
            wrong = wrong_item.text().strip() if wrong_item else ""
            correct = correct_item.text().strip() if correct_item else ""
            if wrong:
                vocab[wrong] = correct
        return vocab

    def on_add_row(self):
        self._add_row()
        self.table.scrollToBottom()
        new_row = self.table.rowCount() - 1
        self.table.setCurrentCell(new_row, 0)
        self.table.editItem(self.table.item(new_row, 0))

    def on_remove_selected(self):
        selected_rows = sorted(
            {index.row() for index in self.table.selectedIndexes()}, reverse=True
        )
        for row in selected_rows:
            self.table.removeRow(row)

    def on_save(self):
        vocab = self._collect_vocab()
        try:
            save_vocab(vocab)
            QMessageBox.information(self, _("Vocabulary"), _("Vocabulary saved successfully."))
        except Exception:
            logging.exception("Failed to save vocabulary")
            QMessageBox.warning(self, _("Vocabulary"), _("Failed to save vocabulary."))

    def on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _("Import Vocabulary"), "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            self.table.setRowCount(0)
            for wrong, correct in data.items():
                self._add_row(str(wrong), str(correct))
            QMessageBox.information(self, _("Vocabulary"), _("Imported %d entries.") % len(data))
        except Exception:
            logging.exception("Failed to import vocabulary")
            QMessageBox.warning(self, _("Vocabulary"), _("Failed to import vocabulary file."))

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, _("Export Vocabulary"), "vocabulary.json", "JSON files (*.json)"
        )
        if not path:
            return
        vocab = self._collect_vocab()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(vocab, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, _("Vocabulary"), _("Exported %d entries.") % len(vocab))
        except Exception:
            logging.exception("Failed to export vocabulary")
            QMessageBox.warning(self, _("Vocabulary"), _("Failed to export vocabulary file."))
