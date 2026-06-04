import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QWidget,
)

from buzz.locale import _
from buzz.vocab_replacement import load_vocab, save_vocab


class AutoReplaceWidget(QGroupBox):
    """Compact inline widget for managing typo replacement rules in the transcription form."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(_("Auto-replace Typos"), parent)
        self.setCheckable(True)
        self.setChecked(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels([_("Wrong (typo)"), _("Correct")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(140)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        self.add_button = QPushButton(_("Add"), self)
        self.add_button.setFixedWidth(70)
        self.add_button.clicked.connect(self.on_add_row)
        button_row.addWidget(self.add_button)

        self.remove_button = QPushButton(_("Remove"), self)
        self.remove_button.setFixedWidth(70)
        self.remove_button.clicked.connect(self.on_remove_selected)
        button_row.addWidget(self.remove_button)

        button_row.addStretch()
        layout.addLayout(button_row)
        self.setLayout(layout)

        self._loading = False
        self._load_vocab()

        self.toggled.connect(self._on_toggled)

    def _load_vocab(self):
        self._loading = True
        try:
            vocab = load_vocab()
            self.table.setRowCount(0)
            for wrong, correct in vocab.items():
                self._add_row(wrong, correct)
            if vocab:
                self.setChecked(True)
        finally:
            self._loading = False

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

    def _save(self):
        if self._loading:
            return
        try:
            vocab = self._collect_vocab() if self.isChecked() else {}
            save_vocab(vocab)
        except Exception:
            logging.exception("Failed to auto-save vocabulary")

    def _on_item_changed(self, _item: QTableWidgetItem):
        self._save()

    def _on_toggled(self, checked: bool):
        if not checked:
            self._save()

    def on_add_row(self):
        self._add_row()
        new_row = self.table.rowCount() - 1
        self.table.scrollToBottom()
        self.table.setCurrentCell(new_row, 0)
        self.table.editItem(self.table.item(new_row, 0))

    def on_remove_selected(self):
        selected_rows = sorted(
            {index.row() for index in self.table.selectedIndexes()}, reverse=True
        )
        for row in selected_rows:
            self.table.removeRow(row)
        self._save()
