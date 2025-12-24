import re
import os
import logging
import ssl
import time
import random
from typing import Optional

# Fix SSL certificate verification for bundled applications (macOS, Windows)
# This must be done before importing libraries that download from Hugging Face
try:
    import certifi
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    os.environ.setdefault('SSL_CERT_DIR', os.path.dirname(certifi.where()))
    # Also update the default SSL context for urllib
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

import faster_whisper
import torch
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

from ctc_forced_aligner.ctc_forced_aligner import (
    generate_emissions,
    get_alignments,
    get_spans,
    load_alignment_model,
    postprocess_results,
    preprocess_text,
)
from whisper_diarization.helpers import (
    get_realigned_ws_mapping_with_punctuation,
    get_sentences_speaker_mapping,
    get_words_speaker_mapping,
    langs_to_iso,
    punct_model_langs,
)
from deepmultilingualpunctuation.deepmultilingualpunctuation import PunctuationModel
from whisper_diarization.diarization import MSDDDiarizer

SENTENCE_END = re.compile(r'.*[.!?。！？]')

class IdentificationWorker(QObject):
    finished = pyqtSignal(list)
    progress_update = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, transcription, transcription_service):
        super().__init__()
        self.transcription = transcription
        self.transcription_service = transcription_service
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation of the worker."""
        self._is_cancelled = True

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
        diarizer_model = None
        alignment_model = None

        try:
            logging.debug("Speaker identification worker: Starting")
            self.progress_update.emit(_("1/8 Collecting transcripts"))

            if self._is_cancelled:
                logging.debug("Speaker identification worker: Cancelled at step 1")
                return

            # Step 1 - Get transcript
            # TODO - Add detected language to the transcript, detect and store separately in metadata
            #        Will also be relevant for template parsing of transcript file names
            #        - See diarize.py for example on how to get this info from whisper transcript, maybe other whisper models also have it
            language = self.transcription.language if self.transcription.language else "en"

            segments = self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )

            full_transcript = "".join(segment.text for segment in segments)

            if self._is_cancelled:
                logging.debug("Speaker identification worker: Cancelled at step 2")
                return

            self.progress_update.emit(_("2/8 Loading audio"))
            audio_waveform = faster_whisper.decode_audio(self.transcription.file)

            # Step 2 - Forced alignment
            force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
            use_cuda = torch.cuda.is_available() and force_cpu == "false"
            device = "cuda" if use_cuda else "cpu"
            torch_dtype = torch.float16 if use_cuda else torch.float32

            logging.debug(f"Speaker identification worker: Using device={device}")

            if self._is_cancelled:
                logging.debug("Speaker identification worker: Cancelled at step 3")
                return

            self.progress_update.emit(_("3/8 Loading alignment model"))
            alignment_model = None
            alignment_tokenizer = None
            for attempt in range(3):
                try:
                    alignment_model, alignment_tokenizer = load_alignment_model(
                        device,
                        dtype=torch_dtype,
                    )
                    break
                except Exception as e:
                    if attempt < 2:
                        logging.warning(
                            f"Speaker identification: Failed to load alignment model "
                            f"(attempt {attempt + 1}/3), retrying: {e}"
                        )
                        # On retry, try using cached models only (offline mode)
                        # Set at runtime by modifying the library constants directly
                        # (env vars are only read at import time)
                        try:
                            import huggingface_hub.constants
                            huggingface_hub.constants.HF_HUB_OFFLINE = True
                            logging.debug("Speaker identification: Enabled HF offline mode")
                        except Exception as offline_err:
                            logging.warning(f"Failed to set offline mode: {offline_err}")
                        self.progress_update.emit(
                            _("3/8 Loading alignment model (retrying with cache...)")
                        )
                        time.sleep(2 ** attempt)  # 1s, 2s backoff
                    else:
                        raise RuntimeError(
                            _("Failed to load alignment model. "
                              "Please check your internet connection and try again.")
                        ) from e

            if self._is_cancelled:
                logging.debug("Speaker identification worker: Cancelled at step 4")
                return

            self.progress_update.emit(_("4/8 Processing audio"))
            emissions, stride = generate_emissions(
                alignment_model,
                torch.from_numpy(audio_waveform)
                .to(alignment_model.dtype)
                .to(alignment_model.device),
                batch_size=8,
            )

            # Clean up alignment model
            del alignment_model
            alignment_model = None
            torch.cuda.empty_cache()

            if self._is_cancelled:
                logging.debug("Speaker identification worker: Cancelled at step 5")
                return

            self.progress_update.emit(_("5/8 Preparing transcripts"))
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

            if self._is_cancelled:
                logging.debug("Speaker identification worker: Cancelled at step 6")
                return

            # Step 3 - Diarization
            self.progress_update.emit(_("6/8 Identifying speakers"))

            # Silence NeMo's verbose logging
            logging.getLogger("nemo_logging").setLevel(logging.ERROR)
            try:
                # Also try to silence NeMo's internal logging system
                from nemo.utils import logging as nemo_logging
                nemo_logging.setLevel(logging.ERROR)
            except (ImportError, AttributeError):
                pass

            logging.debug("Speaker identification worker: Creating diarizer model")
            diarizer_model = MSDDDiarizer(device)
            logging.debug("Speaker identification worker: Running diarization")
            speaker_ts = diarizer_model.diarize(torch.from_numpy(audio_waveform).unsqueeze(0))
            logging.debug("Speaker identification worker: Diarization complete")

            # Clean up diarizer model immediately after use
            del diarizer_model
            diarizer_model = None
            torch.cuda.empty_cache()

            if self._is_cancelled:
                logging.debug("Speaker identification worker: Cancelled at step 7")
                return

            # Step 4 - Reading timestamps <> Speaker Labels mapping
            self.progress_update.emit(_("7/8 Mapping speakers to transcripts"))

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

            logging.debug("Speaker identification worker: Finished successfully")
            self.progress_update.emit(_("8/8 Identification done"))
            self.finished.emit(ssm)

        except Exception as e:
            logging.error(f"Speaker identification worker: Error - {e}", exc_info=True)
            self.progress_update.emit(_("0/0 Error identifying speakers"))
            self.error.emit(str(e))
            # Emit empty list so the UI can reset properly
            self.finished.emit([])

        finally:
            # Ensure cleanup happens regardless of how we exit
            logging.debug("Speaker identification worker: Cleaning up resources")
            if diarizer_model is not None:
                try:
                    del diarizer_model
                except Exception:
                    pass
            if alignment_model is not None:
                try:
                    del alignment_model
                except Exception:
                    pass
            torch.cuda.empty_cache()
            # Reset offline mode so it doesn't affect other operations
            try:
                import huggingface_hub.constants
                huggingface_hub.constants.HF_HUB_OFFLINE = False
            except Exception:
                pass


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
        self.needs_layout_update = False

        self.setMinimumWidth(650)
        self.setMinimumHeight(400)

        self.setWindowTitle(file_path_as_title(transcription.file))

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

        # Progress container with label and bar
        progress_container = QVBoxLayout()

        self.progress_label = QLabel(self)
        if os.path.isfile(self.transcription.file):
            self.progress_label.setText(_("Ready to identify speakers"))
        else:
            self.progress_label.setText(_("Audio file not found"))
            self.step_1_button.setEnabled(False)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMinimumWidth(400)
        self.progress_bar.setRange(0, 8)
        self.progress_bar.setValue(0)

        progress_container.addWidget(self.progress_label)
        progress_container.addWidget(self.progress_bar)

        self.step_1_row.addLayout(progress_container)

        self.step_1_row.addWidget(self.step_1_button, alignment=Qt.AlignmentFlag.AlignTop)

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

    def on_identify_button_clicked(self):
        self.step_1_button.setEnabled(False)

        # Clean up any existing thread before starting a new one
        self._cleanup_thread()

        logging.debug("Speaker identification: Starting identification thread")

        self.thread = QThread()
        self.worker = IdentificationWorker(
            self.transcription,
            self.transcription_service
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_thread_finished)
        self.worker.progress_update.connect(self.on_progress_update)
        self.worker.error.connect(self.on_identification_error)

        self.thread.start()

    def _on_thread_finished(self, result):
        """Handle thread completion and cleanup."""
        logging.debug("Speaker identification: Thread finished")
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(5000)
        self.on_identification_finished(result)

    def on_identification_error(self, error_message):
        """Handle identification error."""
        logging.error(f"Speaker identification error: {error_message}")
        self.step_1_button.setEnabled(True)
        self.progress_bar.setValue(0)

    def on_progress_update(self, progress):
        self.progress_label.setText(progress)

        progress_value = 0
        if progress and progress[0].isdigit():
            progress_value = int(progress[0])
            self.progress_bar.setValue(progress_value)
        else:
            logging.error(f"Invalid progress format: {progress}")

        if progress_value == 8:
            self.step_2_group_box.setEnabled(True)
            self.merge_speaker_sentences.setEnabled(True)
            self.save_button.setEnabled(True)

    def on_identification_finished(self, result):
        self.identification_result = result

        # Handle empty results (error case)
        if not result:
            logging.debug("Speaker identification: Empty result received")
            return

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

        # Trigger layout update to properly size the new widgets
        self.layout().activate()
        self.adjustSize()
        # Schedule update if window is minimized
        self.needs_layout_update = True

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

    def changeEvent(self, event):
        super().changeEvent(event)

        # Handle window activation (restored from minimized or brought to front)
        if self.needs_layout_update:
            self.layout().activate()
            self.adjustSize()
            self.needs_layout_update = False

    def closeEvent(self, event):
        self.hide()

        # Stop media player
        self.player.stop()
        if self.player_timer:
            self.player_timer.stop()

        # Clean up thread if running
        self._cleanup_thread()

        super().closeEvent(event)

    def _cleanup_thread(self):
        """Properly clean up the worker thread."""
        if self.worker is not None:
            # Request cancellation first
            self.worker.cancel()

        if self.thread is not None and self.thread.isRunning():
            logging.debug("Speaker identification: Stopping running thread")
            self.thread.quit()
            if not self.thread.wait(10000):  # Wait up to 10 seconds
                logging.warning("Speaker identification: Thread did not quit, terminating")
                self.thread.terminate()
                if not self.thread.wait(2000):
                    logging.error("Speaker identification: Thread failed to terminate")

        self.thread = None
        self.worker = None
