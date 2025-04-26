import logging
import time
import uuid
import pytest
from pytestqt.qtbot import QtBot
from unittest.mock import MagicMock, patch
from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.speaker_identification_widget import (
    SpeakerIdentificationWidget,
    IdentificationWorker,
)
from tests.audio import test_audio_path

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

        logging.debug(f"==== RESULT ==== {result}")

        assert worker.transcription == transcription
        assert len(result) == 1
        assert isinstance(result[0], list)
        assert result == [[{'end_time': 8904, 'speaker': 'Speaker 0', 'start_time': 140, 'text': 'Bienvenue dans. '}]]

