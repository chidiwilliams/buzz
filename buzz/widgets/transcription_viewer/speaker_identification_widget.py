import re
import os
import logging
import faster_whisper
import torch
import torchaudio
import random
from typing import Optional
from platformdirs import user_cache_dir
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import Qt, QThread, QObject, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QFormLayout,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QCheckBox,
    QGroupBox,
    QSpacerItem,
    QSizePolicy,
    QLayout,
)
from buzz.locale import _
from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.paths import file_path_as_title
from buzz.settings.settings import Settings
from buzz.widgets.line_edit import LineEdit
from buzz.transcriber.transcriber import Segment
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)

from ctc_forced_aligner import (
    generate_emissions,
    get_alignments,
    get_spans,
    load_alignment_model,
    postprocess_results,
    preprocess_text,
)
from whisper_diarization.helpers import (
    cleanup,
    create_config,
    get_realigned_ws_mapping_with_punctuation,
    get_sentences_speaker_mapping,
    get_words_speaker_mapping,
    langs_to_iso,
    punct_model_langs,
)
from deepmultilingualpunctuation import PunctuationModel
from nemo.collections.asr.models.msdd_models import NeuralDiarizer


SENTENCE_END = re.compile(r'.*[.!?。！？]')

class IdentificationWorker(QObject):
    finished = pyqtSignal(list)
    progress_update = pyqtSignal(str)

    def __init__(self, transcription, transcription_options, transcription_service):
        super().__init__()
        self.transcription = transcription
        self.transcription_options = transcription_options
        self.transcription_service = transcription_service

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
        self.progress_update.emit(_("1/9 Collecting transcripts"))

        # Step 1 - Get transcript
        # TODO - Add detected language to the transcript, detect and store separately in metadata
        #        Will also be relevant for template parsing of transcript file names
        #        - See diarize.py for example on how to get this info from whisper transcript, maybe other whisper models also have it
        language = self.transcription.language if self.transcription.language else "en"

        segments = self.transcription_service.get_transcription_segments(
            transcription_id=self.transcription.id_as_uuid
        )

        full_transcript = "".join(segment.text for segment in segments)

        self.progress_update.emit(_("2/9 Loading audio"))
        audio_waveform = faster_whisper.decode_audio(self.transcription.file)

        # Step 2 - Forced alignment
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        use_cuda = torch.cuda.is_available() and force_cpu == "false"
        device = "cuda" if use_cuda else "cpu"
        torch_dtype = torch.float16 if use_cuda else torch.float32

        self.progress_update.emit(_("3/9 Loading alignment model"))
        alignment_model, alignment_tokenizer = load_alignment_model(
            device,
            dtype=torch_dtype,
        )

        self.progress_update.emit(_("4/9 Preparing audio"))
        emissions, stride = generate_emissions(
            alignment_model,
            torch.from_numpy(audio_waveform)
            .to(alignment_model.dtype)
            .to(alignment_model.device),
            batch_size=8,
        )

        del alignment_model
        torch.cuda.empty_cache()

        self.progress_update.emit(_("5/9 Preparing transcripts"))
        tokens_starred, text_starred = preprocess_text(
            full_transcript,
            romanize=True,
            language=langs_to_iso[language],
        )

        segments, scores, blank_token = get_alignments(
            emissions,
            tokens_starred,
            alignment_tokenizer,
        )

        spans = get_spans(tokens_starred, segments, blank_token)

        word_timestamps = postprocess_results(text_starred, spans, stride, scores)

        # convert audio to mono for NeMo compatibility
        self.progress_update.emit(_("6/9 Converting audio"))
        model_root_dir = user_cache_dir("Buzz")
        model_root_dir = os.getenv("BUZZ_MODEL_ROOT", model_root_dir)
        temp_path = os.path.join(model_root_dir, "speaker_identification_temp")
        os.makedirs(temp_path, exist_ok=True)
        torchaudio.save(
            os.path.join(temp_path, "mono_file.wav"),
            torch.from_numpy(audio_waveform).unsqueeze(0).float(),
            16000,
            channels_first=True,
        )

        # Step 3 - Diarization
        self.progress_update.emit(_("7/9 Identifying speakers"))
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("nemo_logger").setLevel(logging.ERROR)

        try:
            msdd_model = NeuralDiarizer(cfg=create_config(temp_path)).to(device)
            msdd_model.diarize()
        except Exception as e:
            self.progress_update.emit(_("0/0 Error identifying speakers"))
            logging.error(f"Error during diarization: {e}")
            return
        finally:
            del msdd_model
            torch.cuda.empty_cache()

        # Step 4 - Reading timestamps <> Speaker Labels mapping
        self.progress_update.emit(_("8/9 Mapping speakers to transcripts"))
        speaker_ts = []
        with open(os.path.join(temp_path, "pred_rttms", "mono_file.rttm"), "r") as f:
            lines = f.readlines()
            for line in lines:
                line_list = line.split(" ")
                s = int(float(line_list[5]) * 1000)
                e = s + int(float(line_list[8]) * 1000)
                speaker_ts.append([s, e, int(line_list[11].split("_")[-1])])

        wsm = get_words_speaker_mapping(word_timestamps, speaker_ts, "start")

        if language in punct_model_langs:
            # restoring punctuation in the transcript to help realign the sentences
            punct_model = PunctuationModel(model="kredor/punctuate-all")

            words_list = list(map(lambda x: x["word"], wsm))

            labled_words = punct_model.predict(words_list, chunk_size=230)

            ending_puncts = ".?!。！？"
            model_puncts = ".,;:!?。！？"

            # We don't want to punctuate U.S.A. with a period. Right?
            is_acronym = lambda x: re.fullmatch(r"\b(?:[a-zA-Z]\.){2,}", x)

            for word_dict, labeled_tuple in zip(wsm, labled_words):
                word = word_dict["word"]
                if (
                        word
                        and labeled_tuple[1] in ending_puncts
                        and (word[-1] not in model_puncts or is_acronym(word))
                ):
                    word += labeled_tuple[1]
                    if word.endswith(".."):
                        word = word.rstrip(".")
                    word_dict["word"] = word

        else:
            logging.warning(
                f"Punctuation restoration is not available for {language} language."
                " Using the original punctuation."
            )

        wsm = get_realigned_ws_mapping_with_punctuation(wsm)
        ssm = get_sentences_speaker_mapping(wsm, speaker_ts)

        cleanup(temp_path)

        self.progress_update.emit(_("9/9 Identification done"))
        self.finished.emit(ssm)


class SpeakerIdentificationWidget(QWidget):
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

        self.identification_result = None

        self.thread = None
        self.worker = None

        self.setMinimumWidth(650)
        self.setMinimumHeight(400)

        self.setWindowTitle(file_path_as_title(transcription.file))

        preferences = self.load_preferences()

        (
            self.transcription_options,
            self.file_transcription_options,
        ) = preferences.to_transcription_options(
            openai_access_token=''
        )

        layout = QFormLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)

        # Step 1: Identify speakers
        step_1_label = QLabel(_("Step 1: Identify speakers"), self)
        font = step_1_label.font()
        font.setWeight(QFont.Weight.Bold)
        step_1_label.setFont(font)
        layout.addRow(step_1_label)

        step_1_group_box = QGroupBox(self)
        step_1_group_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        step_1_layout = QVBoxLayout(step_1_group_box)

        self.step_1_row = QHBoxLayout()

        self.step_1_button = QPushButton(_("Identify"))
        self.step_1_button.setMinimumWidth(200)
        self.step_1_button.clicked.connect(self.on_identify_button_clicked)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimumWidth(400)
        self.progress_bar.setRange(0, 9)
        self.progress_bar.setValue(0)

        if os.path.isfile(self.transcription.file):
            self.progress_bar.setFormat(_("Ready to identify speakers"))
        else:
            self.progress_bar.setFormat(_("Audio file not found"))
            self.step_1_button.setEnabled(False)

        self.step_1_row.addWidget(self.progress_bar)

        self.step_1_row.addWidget(self.step_1_button)

        step_1_layout.addLayout(self.step_1_row)

        layout.addRow(step_1_group_box)

        # Spacer
        spacer = QSpacerItem(0, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        layout.addItem(spacer)

        # Step 2: Name speakers
        step_2_label = QLabel(_("Step 2: Name speakers"), self)
        font = step_2_label.font()
        font.setWeight(QFont.Weight.Bold)
        step_2_label.setFont(font)
        layout.addRow(step_2_label)

        self.step_2_group_box = QGroupBox(self)
        self.step_2_group_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.step_2_group_box.setEnabled(False)
        step_2_layout = QVBoxLayout(self.step_2_group_box)

        self.speaker_preview_row = QVBoxLayout()

        self.speaker_0_input = LineEdit("Speaker 0", self)

        self.speaker_0_preview_button = QPushButton(_("Play sample"))
        self.speaker_0_preview_button.setMinimumWidth(200)
        self.speaker_0_preview_button.clicked.connect(lambda: self.on_speaker_preview("Speaker 0"))

        speaker_0_layout = QHBoxLayout()
        speaker_0_layout.addWidget(self.speaker_0_input)
        speaker_0_layout.addWidget(self.speaker_0_preview_button)

        self.speaker_preview_row.addLayout(speaker_0_layout)

        step_2_layout.addLayout(self.speaker_preview_row)

        layout.addRow(self.step_2_group_box)

        # Save button
        self.merge_speaker_sentences = QCheckBox(_("Merge speaker sentences"))
        self.merge_speaker_sentences.setChecked(True)
        self.merge_speaker_sentences.setEnabled(False)
        self.merge_speaker_sentences.setMinimumWidth(250)

        self.save_button = QPushButton(_("Save"))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.on_save_button_clicked)

        layout.addRow(self.merge_speaker_sentences)
        layout.addRow(self.save_button)

        self.setLayout(layout)

        # Invisible preview player
        url = QUrl.fromLocalFile(self.transcription.file)
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setSource(url)
        self.player_timer = None

    def load_preferences(self):
        self.settings.settings.beginGroup("file_transcriber")
        preferences = FileTranscriptionPreferences.load(settings=self.settings.settings)
        self.settings.settings.endGroup()
        return preferences

    def on_identify_button_clicked(self):
        self.step_1_button.setEnabled(False)

        self.thread = QThread()
        self.worker = IdentificationWorker(
            self.transcription,
            self.transcription_options,
            self.transcription_service
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.on_identification_finished)
        self.worker.progress_update.connect(self.on_progress_update)

        self.thread.start()

    def on_progress_update(self, progress):
        self.progress_bar.setFormat(progress)

        progress_value = 0
        if progress and progress[0].isdigit():
            progress_value = int(progress[0])
            self.progress_bar.setValue(progress_value)
        else:
            logging.error(f"Invalid progress format: {progress}")

        if progress_value == 9:
            self.step_2_group_box.setEnabled(True)
            self.merge_speaker_sentences.setEnabled(True)
            self.save_button.setEnabled(True)

    def on_identification_finished(self, result):
        self.identification_result = result

        unique_speakers = {entry['speaker'] for entry in result}

        while self.speaker_preview_row.count():
            item = self.speaker_preview_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                layout = item.layout()
                if layout:
                    while layout.count():
                        sub_item = layout.takeAt(0)
                        sub_widget = sub_item.widget()
                        if sub_widget:
                            sub_widget.deleteLater()

        for speaker in sorted(unique_speakers):
            speaker_input = LineEdit(speaker, self)
            speaker_input.setMinimumWidth(200)

            speaker_preview_button = QPushButton(_("Play sample"))
            speaker_preview_button.setMinimumWidth(200)
            speaker_preview_button.clicked.connect(lambda checked, s=speaker: self.on_speaker_preview(s))

            speaker_layout = QHBoxLayout()
            speaker_layout.addWidget(speaker_input)
            speaker_layout.addWidget(speaker_preview_button)

            self.speaker_preview_row.addLayout(speaker_layout)

    def on_speaker_preview(self, speaker_id):
        if self.player_timer:
            self.player_timer.stop()

        speaker_records = [record for record in self.identification_result if record['speaker'] == speaker_id]

        if speaker_records:
            random_record = random.choice(speaker_records)

            start_time = random_record['start_time']
            end_time = random_record['end_time']

            self.player.setPosition(int(start_time))
            self.player.play()

            self.player_timer = QTimer(self)
            self.player_timer.setSingleShot(True)
            self.player_timer.timeout.connect(self.player.stop)
            self.player_timer.start(min(end_time, 10 * 1000))  # 10 seconds

    def on_save_button_clicked(self):
        speaker_names = []
        for i in range(self.speaker_preview_row.count()):
            item = self.speaker_preview_row.itemAt(i)
            if item.layout():
                for j in range(item.layout().count()):
                    sub_item = item.layout().itemAt(j)
                    widget = sub_item.widget()
                    if isinstance(widget, LineEdit):
                        speaker_names.append(widget.text())

        unique_speakers = {entry['speaker'] for entry in self.identification_result}
        original_speakers = sorted(unique_speakers)
        speaker_mapping = dict(zip(original_speakers, speaker_names))

        segments = []
        if self.merge_speaker_sentences.isChecked():
            previous_segment = None

            for entry in self.identification_result:
                speaker_name = speaker_mapping.get(entry['speaker'], entry['speaker'])

                if previous_segment and previous_segment['speaker'] == speaker_name:
                    previous_segment['end_time'] = entry['end_time']
                    previous_segment['text'] += " " + entry['text']
                else:
                    if previous_segment:
                        segment = Segment(
                            start=previous_segment['start_time'],
                            end=previous_segment['end_time'],
                            text=f"{previous_segment['speaker']}: {previous_segment['text']}"
                        )
                        segments.append(segment)
                    previous_segment = {
                        'start_time': entry['start_time'],
                        'end_time': entry['end_time'],
                        'speaker': speaker_name,
                        'text': entry['text']
                    }

            if previous_segment:
                segment = Segment(
                    start=previous_segment['start_time'],
                    end=previous_segment['end_time'],
                    text=f"{previous_segment['speaker']}: {previous_segment['text']}"
                )
                segments.append(segment)
        else:
            for entry in self.identification_result:
                speaker_name = speaker_mapping.get(entry['speaker'], entry['speaker'])
                segment = Segment(
                    start=entry['start_time'],
                    end=entry['end_time'],
                    text=f"{speaker_name}: {entry['text']}"
                )
                segments.append(segment)

        new_transcript_id = self.transcription_service.copy_transcription(
            self.transcription.id_as_uuid
        )

        self.transcription_service.update_transcription_as_completed(new_transcript_id, segments)

        # TODO - See if we can get rows in the transcription viewer to be of variable height
        #        If text is longer they should expand
        if self.transcriptions_updated_signal:
            self.transcriptions_updated_signal.emit(new_transcript_id)

        self.player.stop()

        if self.player_timer:
            self.player_timer.stop()

        self.close()

    def closeEvent(self, event):
        self.hide()

        super().closeEvent(event)
