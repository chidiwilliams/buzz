import logging
import platform
import time
import uuid
import pytest
from pytestqt.qtbot import QtBot
from unittest.mock import MagicMock, patch
from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
# Underlying libs do not support intel Macs or Windows (nemo C extensions crash on Windows CI)
if not (platform.system() == "Darwin" and platform.machine() == "x86_64") and platform.system() != "Windows":
    from buzz.widgets.transcription_viewer.speaker_identification_widget import (
        SpeakerIdentificationWidget,
        IdentificationWorker,
        process_in_batches,
    )
from tests.audio import test_audio_path

@pytest.mark.skipif(
    (platform.system() == "Darwin" and platform.machine() == "x86_64") or platform.system() == "Windows",
    reason="Speaker identification dependencies (nemo/texterrors C extensions) crash on Windows and are unsupported on Intel Mac"
)
class TestSpeakerIdentificationWidget:
    @pytest.fixture()
    def transcription(
        self, transcription_dao, transcription_segment_dao
    ) -> Transcription:
        id = uuid.uuid4()
        transcription_dao.insert(
            Transcription(
                id=str(id),
                status="completed",
                file=test_audio_path,
                task=Task.TRANSCRIBE.value,
                model_type=ModelType.WHISPER.value,
                whisper_model_size=WhisperModelSize.SMALL.value,
            )
        )
        transcription_segment_dao.insert(TranscriptionSegment(40, 299, "Bien", "", str(id)))
        transcription_segment_dao.insert(
            TranscriptionSegment(299, 329, "venue dans", "", str(id))
        )

        return transcription_dao.find_by_id(str(id))

    def test_widget_initialization(self, qtbot: QtBot, transcription, transcription_service):
        """Test the initialization of SpeakerIdentificationWidget."""
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        assert widget.transcription == transcription
        assert widget.transcription_service == transcription_service
        assert widget.progress_bar.value() == 0

        widget.close()

        # Wait to clean-up threads
        time.sleep(3)

    @pytest.mark.skipif(
        platform.system() == "Linux",
        reason="Skip speaker identification worker test on Linux, CI freezes"
    )
    @patch("buzz.widgets.transcription_viewer.speaker_identification_widget.IdentificationWorker")
    def test_identification_worker_run(self, qtbot: QtBot, transcription, transcription_service):
        """Test the IdentificationWorker's run method and capture the finished signal result."""
        worker = IdentificationWorker(
            transcription=transcription,
            transcription_service=transcription_service,
        )

        result = []

        def capture_result(data):
            result.append(data)

        worker.finished.connect(capture_result)

        with qtbot.waitSignal(worker.finished, timeout= 300000): #5 min timeout
            worker.run()

        assert worker.transcription == transcription
        assert len(result) == 1
        assert isinstance(result[0], list)
        assert (result == [[{'end_time': 8904, 'speaker': 'Speaker 0', 'start_time': 140, 'text': 'Bien venue dans. '}]]
                or result == [[{'end_time': 8904, 'speaker': 'Speaker 0', 'start_time': 140, 'text': 'Bienvenue dans. '}]])

    def test_identify_button_toggles_visibility(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        # Before: identify visible, cancel hidden
        assert not widget.step_1_button.isHidden()
        assert widget.cancel_button.isHidden()

        from PyQt6.QtCore import QThread as RealQThread
        mock_thread = MagicMock(spec=RealQThread)
        mock_thread.started = MagicMock()
        mock_thread.started.connect = MagicMock()

        with patch.object(widget, '_cleanup_thread'), \
             patch('buzz.widgets.transcription_viewer.speaker_identification_widget.QThread', return_value=mock_thread), \
             patch.object(widget, 'worker', create=True):
            # patch moveToThread on IdentificationWorker to avoid type error
            with patch.object(IdentificationWorker, 'moveToThread'):
                widget.on_identify_button_clicked()

        # After: identify hidden, cancel visible
        assert widget.step_1_button.isHidden()
        assert not widget.cancel_button.isHidden()

        widget.close()

    def test_cancel_button_resets_ui(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        # Simulate identification started
        widget.step_1_button.setVisible(False)
        widget.cancel_button.setVisible(True)

        with patch.object(widget, '_cleanup_thread'):
            widget.on_cancel_button_clicked()

        assert not widget.step_1_button.isHidden()
        assert widget.cancel_button.isHidden()
        assert widget.progress_bar.value() == 0
        assert len(widget.progress_label.text()) > 0

        widget.close()

    def test_on_progress_update_sets_label_and_bar(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        widget.on_progress_update("3/8 Loading alignment model")

        assert widget.progress_label.text() == "3/8 Loading alignment model"
        assert widget.progress_bar.value() == 3

        widget.close()

    def test_on_progress_update_step_8_enables_save(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        assert not widget.save_button.isEnabled()

        widget.on_progress_update("8/8 Identification done")

        assert widget.save_button.isEnabled()
        assert widget.step_2_group_box.isEnabled()
        assert widget.merge_speaker_sentences.isEnabled()

        widget.close()

    def test_on_identification_finished_empty_result(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        initial_row_count = widget.speaker_preview_row.count()

        widget.on_identification_finished([])

        assert widget.identification_result == []
        # Empty result returns early — speaker preview row unchanged
        assert widget.speaker_preview_row.count() == initial_row_count

        widget.close()

    def test_on_identification_finished_populates_speakers(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        result = [
            {'speaker': 'Speaker 0', 'start_time': 0, 'end_time': 3000, 'text': 'Hello world.'},
            {'speaker': 'Speaker 1', 'start_time': 3000, 'end_time': 6000, 'text': 'Hi there.'},
        ]
        widget.on_identification_finished(result)

        assert widget.identification_result == result
        # Two speaker rows should have been created
        assert widget.speaker_preview_row.count() == 2

        widget.close()

    def test_on_identification_error_resets_buttons(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        widget.step_1_button.setVisible(False)
        widget.cancel_button.setVisible(True)

        widget.on_identification_error("Some error")

        assert not widget.step_1_button.isHidden()
        assert widget.cancel_button.isHidden()
        assert widget.progress_bar.value() == 0

        widget.close()

    def test_on_save_no_merge(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        result = [
            {'speaker': 'Speaker 0', 'start_time': 0, 'end_time': 2000, 'text': 'Hello.'},
            {'speaker': 'Speaker 0', 'start_time': 2000, 'end_time': 4000, 'text': 'World.'},
            {'speaker': 'Speaker 1', 'start_time': 4000, 'end_time': 6000, 'text': 'Hi.'},
        ]
        widget.on_identification_finished(result)
        widget.merge_speaker_sentences.setChecked(False)

        with patch.object(widget.transcription_service, 'copy_transcription', return_value=uuid.uuid4()) as mock_copy, \
             patch.object(widget.transcription_service, 'update_transcription_as_completed') as mock_update:
            widget.on_save_button_clicked()

        mock_copy.assert_called_once()
        mock_update.assert_called_once()
        segments = mock_update.call_args[0][1]
        # No merge: 3 entries → 3 segments
        assert len(segments) == 3

        widget.close()

    def test_on_save_with_merge(self, qtbot: QtBot, transcription, transcription_service):
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
        )
        qtbot.addWidget(widget)

        result = [
            {'speaker': 'Speaker 0', 'start_time': 0, 'end_time': 2000, 'text': 'Hello.'},
            {'speaker': 'Speaker 0', 'start_time': 2000, 'end_time': 4000, 'text': 'World.'},
            {'speaker': 'Speaker 1', 'start_time': 4000, 'end_time': 6000, 'text': 'Hi.'},
        ]
        widget.on_identification_finished(result)
        widget.merge_speaker_sentences.setChecked(True)

        with patch.object(widget.transcription_service, 'copy_transcription', return_value=uuid.uuid4()), \
             patch.object(widget.transcription_service, 'update_transcription_as_completed') as mock_update:
            widget.on_save_button_clicked()

        segments = mock_update.call_args[0][1]
        # Merge: two consecutive Speaker 0 entries → merged into 1; Speaker 1 → 1 = 2 total
        assert len(segments) == 2
        assert "Speaker 0" in segments[0].text
        assert "Hello." in segments[0].text
        assert "World." in segments[0].text

        widget.close()

    def test_on_save_emits_transcriptions_updated(self, qtbot: QtBot, transcription, transcription_service):
        updated_signal = MagicMock()
        widget = SpeakerIdentificationWidget(
            transcription=transcription,
            transcription_service=transcription_service,
            transcriptions_updated_signal=updated_signal,
        )
        qtbot.addWidget(widget)

        result = [{'speaker': 'Speaker 0', 'start_time': 0, 'end_time': 1000, 'text': 'Hi.'}]
        widget.on_identification_finished(result)

        new_id = uuid.uuid4()
        with patch.object(widget.transcription_service, 'copy_transcription', return_value=new_id), \
             patch.object(widget.transcription_service, 'update_transcription_as_completed'):
            widget.on_save_button_clicked()

        updated_signal.emit.assert_called_once_with(new_id)

        widget.close()

    def test_batch_processing_with_many_words(self):
        """Test batch processing when there are more than 200 words."""
        # Create mock punctuation model
        mock_punct_model = MagicMock()
        mock_punct_model.predict.side_effect = lambda batch, chunk_size: [
            (word.strip(), ".") for word in batch
        ]
        
        # Create words list with 201 words (just enough to trigger batch processing)
        words_list = [f"word{i}" for i in range(201)]
        
        # Wrap predict method to match the expected signature
        def predict_wrapper(batch, chunk_size, **kwargs):
            return mock_punct_model.predict(batch, chunk_size=chunk_size)
        
        # Call the generic batch processing function
        result = process_in_batches(
            items=words_list,
            process_func=predict_wrapper
        )
        
        # Verify that predict was called multiple times (for batches)
        assert mock_punct_model.predict.call_count >= 2, "Batch processing should split into multiple calls"
        
        # Verify that each batch was processed with correct chunk_size
        for call in mock_punct_model.predict.call_args_list:
            args, kwargs = call
            batch = args[0]
            chunk_size = kwargs.get('chunk_size')
            assert chunk_size <= 230, "Chunk size should not exceed 230"
            assert len(batch) <= 200, "Batch size should not exceed 200"
        
        # Verify result contains all words
        assert len(result) == 201, "Result should contain all words"

    def test_batch_processing_with_assertion_error_fallback(self):
        """Test error handling when AssertionError occurs during batch processing."""
        # Create mock punctuation model - raise AssertionError on first batch, then succeed
        mock_punct_model = MagicMock()
        call_count = [0]
        
        def predict_side_effect(batch, chunk_size):
            call_count[0] += 1
            # Raise AssertionError on first call (first batch)
            if call_count[0] == 1:
                raise AssertionError("Chunk size too large")
            # Succeed on subsequent calls (smaller batches)
            return [(word.strip(), ".") for word in batch]
        
        mock_punct_model.predict.side_effect = predict_side_effect
        
        # Create words list with 201 words (enough to trigger batch processing)
        words_list = [f"word{i}" for i in range(201)]
        
        # Wrap predict method to match the expected signature
        def predict_wrapper(batch, chunk_size, **kwargs):
            return mock_punct_model.predict(batch, chunk_size=chunk_size)
        
        # Call the generic batch processing function
        result = process_in_batches(
            items=words_list,
            process_func=predict_wrapper
        )
        
        # Verify that predict was called multiple times
        # First call fails, then smaller batches succeed
        assert mock_punct_model.predict.call_count > 1, "Should retry with smaller batches after AssertionError"
        
        # Verify that smaller batches were used after the error
        call_args_list = mock_punct_model.predict.call_args_list
        # After the first failed call, subsequent calls should have smaller batches
        for i, call in enumerate(call_args_list[1:], start=1):  # Skip first failed call
            args, kwargs = call
            batch = args[0]
            assert len(batch) <= 100, f"After AssertionError, batch size should be <= 100, got {len(batch)}"
        
        # Verify result contains all words
        assert len(result) == 201, "Result should contain all words"

