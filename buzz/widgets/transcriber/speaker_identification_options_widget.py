"""Options to identify speakers right after a file is transcribed.

Used by the file import dialog and the folder watch preferences.
"""

import platform
from dataclasses import dataclass, replace
from typing import Optional

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from buzz.locale import _

DIARIZERS = ("msdd", "sortformer")
DEFAULT_DIARIZER = "msdd"


def is_speaker_identification_available() -> bool:
    # Its libraries do not support Intel Macs
    return not (platform.system() == "Darwin" and platform.machine() == "x86_64")


@dataclass
class SpeakerIdentificationOptions:
    identify_speakers: bool = False
    speaker_diarizer: str = DEFAULT_DIARIZER
    # None to detect the number of speakers. Only MSDD takes a count.
    speaker_count: Optional[int] = None
    merge_speaker_sentences: bool = True

    def save(self, settings: QSettings) -> None:
        settings.setValue("identify_speakers", self.identify_speakers)
        settings.setValue("speaker_diarizer", self.speaker_diarizer)
        settings.setValue(
            "speaker_count", "" if self.speaker_count is None else self.speaker_count
        )
        settings.setValue("merge_speaker_sentences", self.merge_speaker_sentences)

    @classmethod
    def load(cls, settings: QSettings) -> "SpeakerIdentificationOptions":
        speaker_diarizer = settings.value(
            "speaker_diarizer", defaultValue=DEFAULT_DIARIZER, type=str
        )
        if speaker_diarizer not in DIARIZERS:
            speaker_diarizer = DEFAULT_DIARIZER

        try:
            speaker_count = int(settings.value("speaker_count", ""))
        except (TypeError, ValueError):
            speaker_count = None

        return SpeakerIdentificationOptions(
            identify_speakers=_load_bool(settings, "identify_speakers", False),
            speaker_diarizer=speaker_diarizer,
            speaker_count=speaker_count,
            merge_speaker_sentences=_load_bool(
                settings, "merge_speaker_sentences", True
            ),
        )


def _load_bool(settings: QSettings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    return False if value == "false" else bool(value)


class SpeakerIdentificationOptionsWidget(QWidget):
    """Identify speakers checkbox with the diarizer, speaker count and merge
    options, which are enabled only while the checkbox is checked."""

    options_changed = pyqtSignal(SpeakerIdentificationOptions)

    def __init__(
        self,
        options: SpeakerIdentificationOptions,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.options = replace(options)
        self._enabled = True

        self.identify_speakers_checkbox = QCheckBox(_("Identify speakers"), self)
        self.identify_speakers_checkbox.setChecked(self.options.identify_speakers)
        self.identify_speakers_checkbox.setObjectName("IdentifySpeakersCheckbox")
        self.identify_speakers_checkbox.setToolTip(
            _(
                "Identify speakers after transcription and add speaker labels "
                "to the exported transcripts. Transcription will take longer."
            )
        )
        self.identify_speakers_checkbox.stateChanged.connect(
            self._on_identify_speakers_changed
        )

        self.diarizer_combo_box = QComboBox(self)
        self.diarizer_combo_box.setObjectName("SpeakerDiarizerComboBox")
        self.diarizer_combo_box.addItem(_("MSDD"), "msdd")
        self.diarizer_combo_box.addItem(_("Sortformer"), "sortformer")
        self.diarizer_combo_box.setCurrentIndex(
            max(self.diarizer_combo_box.findData(self.options.speaker_diarizer), 0)
        )
        self.diarizer_combo_box.currentIndexChanged.connect(self._on_diarizer_changed)

        self.speaker_count_combo_box = QComboBox(self)
        self.speaker_count_combo_box.setObjectName("SpeakerCountComboBox")
        self.speaker_count_combo_box.addItem(_("Auto"), None)
        for speaker_count in range(2, 9):
            self.speaker_count_combo_box.addItem(str(speaker_count), speaker_count)
        self.speaker_count_combo_box.setCurrentIndex(
            max(self.speaker_count_combo_box.findData(self.options.speaker_count), 0)
        )
        self.speaker_count_combo_box.setToolTip(
            _("Set the known number of speakers, or use Auto to detect it.")
        )
        self.speaker_count_combo_box.currentIndexChanged.connect(
            self._on_speaker_count_changed
        )

        self.merge_speaker_sentences_checkbox = QCheckBox(
            _("Merge speaker sentences"), self
        )
        self.merge_speaker_sentences_checkbox.setChecked(
            self.options.merge_speaker_sentences
        )
        self.merge_speaker_sentences_checkbox.setObjectName(
            "MergeSpeakerSentencesCheckbox"
        )
        self.merge_speaker_sentences_checkbox.stateChanged.connect(
            self._on_merge_speaker_sentences_changed
        )

        model_row = QHBoxLayout()
        model_row.addWidget(self.diarizer_combo_box)
        model_row.addSpacing(12)
        model_row.addWidget(QLabel(_("Speakers:"), self))
        model_row.addWidget(self.speaker_count_combo_box)
        model_row.addStretch()

        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("", self.identify_speakers_checkbox)
        layout.addRow(_("Model"), model_row)
        layout.addRow("", self.merge_speaker_sentences_checkbox)

        self._update_enabled()

    def set_options_enabled(self, enabled: bool) -> None:
        """Enable or disable all options, e.g. while folder watch is off."""
        self._enabled = enabled
        self._update_enabled()

    def _update_enabled(self) -> None:
        self.identify_speakers_checkbox.setEnabled(self._enabled)
        enabled = self._enabled and self.options.identify_speakers
        self.diarizer_combo_box.setEnabled(enabled)
        self.speaker_count_combo_box.setEnabled(
            enabled and self.options.speaker_diarizer == "msdd"
        )
        self.merge_speaker_sentences_checkbox.setEnabled(enabled)

    def _emit_changed(self) -> None:
        self.options_changed.emit(replace(self.options))

    def _on_identify_speakers_changed(self, state: int) -> None:
        self.options.identify_speakers = state == 2
        self._update_enabled()
        self._emit_changed()

    def _on_diarizer_changed(self, _index: int) -> None:
        self.options.speaker_diarizer = self.diarizer_combo_box.currentData()
        self._update_enabled()
        self._emit_changed()

    def _on_speaker_count_changed(self, _index: int) -> None:
        self.options.speaker_count = self.speaker_count_combo_box.currentData()
        self._emit_changed()

    def _on_merge_speaker_sentences_changed(self, state: int) -> None:
        self.options.merge_speaker_sentences = state == 2
        self._emit_changed()
