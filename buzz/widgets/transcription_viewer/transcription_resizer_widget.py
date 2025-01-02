import re
import os
import logging
import stable_whisper
import srt
from pathlib import Path
from srt_equalizer import srt_equalizer
from typing import Optional
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QFormLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QPushButton,
    QCheckBox,
    QGroupBox,
    QSpacerItem,
    QSizePolicy,
)
from buzz.locale import _, languages
from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.paths import file_path_as_title
from buzz.settings.settings import Settings
from buzz.widgets.line_edit import LineEdit
from buzz.transcriber.transcriber import Segment
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)


SENTENCE_END = re.compile(r'.*[.!?。！？]')

class TranscriptionWorker(QObject):
    finished = pyqtSignal()
    result_ready = pyqtSignal(list)

    def __init__(self, transcription, transcription_options, transcription_service, regroup_string: str):
        super().__init__()
        self.transcription = transcription
        self.transcription_options = transcription_options
        self.transcription_service = transcription_service
        self.regroup_string = regroup_string

    def get_transcript(self, audio, **kwargs) -> dict:
        buzz_segments = self.transcription_service.get_transcription_segments(
            transcription_id=self.transcription.id_as_uuid
        )

        segments = []
        words = []
        text = ""
        for buzz_segment in buzz_segments:
            words.append({
                'word': buzz_segment.text + " ",
                'start': buzz_segment.start_time / 100,
                'end': buzz_segment.end_time / 100,
            })
            text += buzz_segment.text + " "

            if SENTENCE_END.match(buzz_segment.text):
                segments.append({
                    'text': text,
                    'words': words
                })
                words = []
                text = ""

        return {
            'language': self.transcription.language,
            'segments': segments
        }

    def run(self):
        transcription_file = self.transcription.file
        transcription_file_exists = os.path.exists(transcription_file)

        transcription_file_path = Path(transcription_file)
        speech_path = transcription_file_path.with_name(f"{transcription_file_path.stem}_speech.flac")
        if self.transcription_options.extract_speech and os.path.exists(speech_path):
            transcription_file = str(speech_path)
            transcription_file_exists = True

        result = stable_whisper.transcribe_any(
            self.get_transcript,
            transcription_file,
            vad=transcription_file_exists,
            suppress_silence=transcription_file_exists,
            regroup=self.regroup_string,
            check_sorted=False,
        )

        segments = []
        for segment in result.segments:
            segments.append(
                Segment(
                    start=int(segment.start * 100),
                    end=int(segment.end * 100),
                    text=segment.text
                )
            )

        self.result_ready.emit(segments)
        self.finished.emit()


class TranscriptionResizerWidget(QWidget):
    resize_button_clicked = pyqtSignal()
    transcription: Transcription
    settings = Settings()

    def __init__(
        self,
        transcription: Transcription,
        transcription_service: TranscriptionService,
        parent: Optional["QWidget"] = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
        transcriptions_updated_signal: Optional[pyqtSignal] = None,
    ) -> None:
        super().__init__(parent, flags)
        self.transcription = transcription
        self.transcription_service = transcription_service
        self.transcriptions_updated_signal = transcriptions_updated_signal

        self.new_transcript_id = None
        self.thread = None
        self.worker = None

        self.setMinimumWidth(600)
        self.setMinimumHeight(300)

        self.setWindowTitle(file_path_as_title(transcription.file))

        preferences = self.load_preferences()

        (
            self.transcription_options,
            self.file_transcription_options,
        ) = preferences.to_transcription_options(
            openai_access_token=''
        )

        layout = QFormLayout(self)

        # Resize longer subtitles
        resize_label = QLabel(_("Resize Options"), self)
        font = resize_label.font()
        font.setWeight(QFont.Weight.Bold)
        resize_label.setFont(font)
        layout.addRow(resize_label)

        resize_group_box = QGroupBox(self)
        resize_layout = QVBoxLayout(resize_group_box)

        self.resize_row = QHBoxLayout()

        self.desired_subtitle_length_label = QLabel(_("Desired subtitle length"), self)

        self.target_chars_spin_box = QSpinBox(self)
        self.target_chars_spin_box.setMinimum(1)
        self.target_chars_spin_box.setMaximum(100)
        self.target_chars_spin_box.setValue(42)

        self.resize_button = QPushButton(_("Resize"))
        self.resize_button.clicked.connect(self.on_resize_button_clicked)

        self.resize_row.addWidget(self.desired_subtitle_length_label)
        self.resize_row.addWidget(self.target_chars_spin_box)
        self.resize_row.addWidget(self.resize_button)

        resize_layout.addLayout(self.resize_row)

        resize_group_box.setEnabled(self.transcription.word_level_timings != 1)

        layout.addRow(resize_group_box)

        # Spacer
        spacer = QSpacerItem(0, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout.addItem(spacer)

        # Merge words into subtitles
        merge_options_label = QLabel(_("Merge Options"), self)
        font = merge_options_label.font()
        font.setWeight(QFont.Weight.Bold)
        merge_options_label.setFont(font)
        layout.addRow(merge_options_label)

        merge_options_group_box = QGroupBox(self)
        merge_options_layout = QVBoxLayout(merge_options_group_box)

        self.merge_options_row = QVBoxLayout()

        self.merge_by_gap = QCheckBox(_("Merge by gap"))
        self.merge_by_gap.setChecked(True)
        self.merge_by_gap.setMinimumWidth(250)
        self.merge_by_gap_input = LineEdit("0.2", self)
        merge_by_gap_layout = QHBoxLayout()
        merge_by_gap_layout.addWidget(self.merge_by_gap)
        merge_by_gap_layout.addWidget(self.merge_by_gap_input)

        self.split_by_punctuation = QCheckBox(_("Split by punctuation"))
        self.split_by_punctuation.setChecked(True)
        self.split_by_punctuation.setMinimumWidth(250)
        self.split_by_punctuation_input = LineEdit(".* /./. /。/?/? /？/!/! /！/,/, ", self)
        split_by_punctuation_layout = QHBoxLayout()
        split_by_punctuation_layout.addWidget(self.split_by_punctuation)
        split_by_punctuation_layout.addWidget(self.split_by_punctuation_input)

        self.split_by_max_length = QCheckBox(_("Split by max length"))
        self.split_by_max_length.setChecked(True)
        self.split_by_max_length.setMinimumWidth(250)
        self.split_by_max_length_input = LineEdit("42", self)
        split_by_max_length_layout = QHBoxLayout()
        split_by_max_length_layout.addWidget(self.split_by_max_length)
        split_by_max_length_layout.addWidget(self.split_by_max_length_input)

        self.merge_options_row.addLayout(merge_by_gap_layout)
        self.merge_options_row.addLayout(split_by_punctuation_layout)
        self.merge_options_row.addLayout(split_by_max_length_layout)

        self.merge_button = QPushButton(_("Merge"))
        self.merge_button.clicked.connect(self.on_merge_button_clicked)

        self.merge_options_row.addWidget(self.merge_button)

        merge_options_layout.addLayout(self.merge_options_row)

        merge_options_group_box.setEnabled(self.transcription.word_level_timings == 1)

        layout.addRow(merge_options_group_box)

        self.setLayout(layout)

    def load_preferences(self):
        self.settings.settings.beginGroup("file_transcriber")
        preferences = FileTranscriptionPreferences.load(settings=self.settings.settings)
        self.settings.settings.endGroup()
        return preferences

    def on_resize_button_clicked(self):
        segments = self.transcription_service.get_transcription_segments(
            transcription_id=self.transcription.id_as_uuid
        )

        subs = []
        for segment in segments:
            subtitle = srt.Subtitle(
                index=segment.id,
                start=segment.start_time,
                end=segment.end_time,
                content=segment.text
            )
            subs.append(subtitle)

        resized_subs = []
        last_index = 0

        # Limit each subtitle to a maximum character length, splitting into
        # multiple subtitle items if necessary.
        for sub in subs:
            new_subs = srt_equalizer.split_subtitle(
                sub=sub, target_chars=self.target_chars_spin_box.value(), start_from_index=last_index, method="punctuation")
            last_index = new_subs[-1].index
            resized_subs.extend(new_subs)

        segments = [
            Segment(
                round(sub.start),
                round(sub.end),
                sub.content
            )
            for sub in resized_subs
            if round(sub.start) != round(sub.end)
        ]

        new_transcript_id = self.transcription_service.copy_transcription(
            self.transcription.id_as_uuid
        )
        self.transcription_service.update_transcription_as_completed(new_transcript_id, segments)

        if self.transcriptions_updated_signal:
            self.transcriptions_updated_signal.emit(new_transcript_id)

    def on_merge_button_clicked(self):
        self.new_transcript_id = self.transcription_service.copy_transcription(
            self.transcription.id_as_uuid
        )
        self.transcription_service.update_transcription_progress(self.new_transcript_id, 0.0)

        if self.transcriptions_updated_signal:
            self.transcriptions_updated_signal.emit(self.new_transcript_id)

        regroup_string = ''
        if self.merge_by_gap.isChecked():
            regroup_string += f'mg={self.merge_by_gap_input.text()}'

            if self.split_by_max_length.isChecked():
                regroup_string += f'++{self.split_by_max_length_input.text()}+1'

        if self.split_by_punctuation.isChecked():
            if regroup_string:
                regroup_string += '_'
            regroup_string += f'sp={self.split_by_punctuation_input.text()}'

        if self.split_by_max_length.isChecked():
            if regroup_string:
                regroup_string += '_'
            regroup_string += f'sl={self.split_by_max_length_input.text()}'

        if self.merge_by_gap.isChecked():
            if regroup_string:
                regroup_string += '_'
            regroup_string += f'mg={self.merge_by_gap_input.text()}'

            if self.split_by_max_length.isChecked():
                regroup_string += f'++{self.split_by_max_length_input.text()}+1'

        regroup_string = os.getenv("BUZZ_MERGE_REGROUP_RULE", regroup_string)

        self.hide()

        self.thread = QThread()
        self.worker = TranscriptionWorker(
            self.transcription,
            self.transcription_options,
            self.transcription_service,
            regroup_string
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.result_ready.connect(self.on_transcription_completed)

        self.thread.start()

    def on_transcription_completed(self, segments):
        if self.new_transcript_id is not None:
            self.transcription_service.update_transcription_as_completed(self.new_transcript_id, segments)

            if self.transcriptions_updated_signal:
                self.transcriptions_updated_signal.emit(self.new_transcript_id)

        self.close()

    def closeEvent(self, event):
        self.hide()

        super().closeEvent(event)
