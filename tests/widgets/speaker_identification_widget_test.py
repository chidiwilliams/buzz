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
# Underlying libs do not support intel Macs
if not (platform.system() == "Darwin" and platform.machine() == "x86_64"):
    from buzz.widgets.transcription_viewer.speaker_identification_widget import (
        SpeakerIdentificationWidget,
        IdentificationWorker,
        process_in_batches,
    )
from tests.audio import test_audio_path

@pytest.mark.skipif(
    platform.system() == "Darwin" and platform.machine() == "x86_64",
    reason="Skip speaker identification tests on macOS x86_64"
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
        assert result == [[{'end_time': 8904, 'speaker': 'Speaker 0', 'start_time': 140, 'text': 'Bienvenue dans. '}]]

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

