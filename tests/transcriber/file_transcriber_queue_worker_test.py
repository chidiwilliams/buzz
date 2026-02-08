import pytest
import unittest.mock
import uuid
from PyQt6.QtCore import QCoreApplication, QThread
from buzz.file_transcriber_queue_worker import FileTranscriberQueueWorker
from buzz.model_loader import ModelType, TranscriptionModel, WhisperModelSize
from buzz.transcriber.transcriber import FileTranscriptionTask, TranscriptionOptions, FileTranscriptionOptions, Segment
from buzz.transcriber.whisper_file_transcriber import WhisperFileTranscriber
from tests.audio import test_multibyte_utf8_audio_path
import time


@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app
    app.quit()


@pytest.fixture
def worker(qapp):
    worker = FileTranscriberQueueWorker()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    thread.start()
    yield worker
    worker.stop()
    thread.quit()
    thread.wait()


@pytest.fixture
def simple_worker(qapp):
    """A non-threaded worker for unit tests that only test individual methods."""
    worker = FileTranscriberQueueWorker()
    yield worker


class TestFileTranscriberQueueWorker:
    def test_cancel_task_adds_to_canceled_set(self, simple_worker):
        task_id = uuid.uuid4()
        simple_worker.cancel_task(task_id)
        assert task_id in simple_worker.canceled_tasks

    def test_add_task_removes_from_canceled(self, simple_worker):
        options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY),
            extract_speech=False
        )
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )

        # First cancel it
        simple_worker.cancel_task(task.uid)
        assert task.uid in simple_worker.canceled_tasks

        # Prevent trigger_run from starting the run loop
        simple_worker.is_running = True
        # Then add it back
        simple_worker.add_task(task)
        assert task.uid not in simple_worker.canceled_tasks

    def test_on_task_error_with_cancellation(self, simple_worker):
        options = TranscriptionOptions()
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )
        simple_worker.current_task = task

        error_spy = unittest.mock.Mock()
        simple_worker.task_error.connect(error_spy)

        simple_worker.on_task_error("Transcription was canceled")

        error_spy.assert_called_once()
        assert task.status == FileTranscriptionTask.Status.CANCELED
        assert "canceled" in task.error.lower()

    def test_on_task_error_with_regular_error(self, simple_worker):
        options = TranscriptionOptions()
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )
        simple_worker.current_task = task

        error_spy = unittest.mock.Mock()
        simple_worker.task_error.connect(error_spy)

        simple_worker.on_task_error("Some error occurred")

        error_spy.assert_called_once()
        assert task.status == FileTranscriptionTask.Status.FAILED
        assert task.error == "Some error occurred"

    def test_on_task_progress_conversion(self, simple_worker):
        options = TranscriptionOptions()
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )
        simple_worker.current_task = task

        progress_spy = unittest.mock.Mock()
        simple_worker.task_progress.connect(progress_spy)

        simple_worker.on_task_progress((50, 100))

        progress_spy.assert_called_once()
        args = progress_spy.call_args[0]
        assert args[0] == task
        assert args[1] == 0.5

    def test_stop_puts_sentinel_in_queue(self, simple_worker):
        initial_size = simple_worker.tasks_queue.qsize()
        simple_worker.stop()
        # Sentinel (None) should be added to queue
        assert simple_worker.tasks_queue.qsize() == initial_size + 1


def test_transcription_with_whisper_cpp_tiny_no_speech_extraction(worker):
    options = TranscriptionOptions(
        model=TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY),
        extract_speech=False
    )
    task = FileTranscriptionTask(file_path=str(test_multibyte_utf8_audio_path), transcription_options=options,
                                 file_transcription_options=FileTranscriptionOptions(), model_path="mock_path")

    with unittest.mock.patch.object(WhisperFileTranscriber, 'run') as mock_run:
        mock_run.side_effect = lambda: worker.current_transcriber.completed.emit([
            {"start": 0, "end": 1000, "text": "Test transcription."}
        ])

        completed_spy = unittest.mock.Mock()
        worker.task_completed.connect(completed_spy)
        worker.add_task(task)

        # Wait for the signal to be emitted
        timeout = 10  # seconds
        start_time = time.time()
        while not completed_spy.called and (time.time() - start_time) < timeout:
            QCoreApplication.processEvents()
            time.sleep(0.1)

        completed_spy.assert_called_once()
        args, kwargs = completed_spy.call_args
        assert args[0] == task
        assert len(args[1]) > 0
        assert args[1][0]["text"] == "Test transcription."


def test_transcription_with_whisper_cpp_tiny_with_speech_extraction(worker):
    options = TranscriptionOptions(
        model=TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY),
        extract_speech=True
    )
    task = FileTranscriptionTask(file_path=str(test_multibyte_utf8_audio_path), transcription_options=options,
                                 file_transcription_options=FileTranscriptionOptions(), model_path="mock_path")

    with unittest.mock.patch('demucs.api.Separator') as mock_separator_class, \
            unittest.mock.patch('demucs.api.save_audio') as mock_save_audio, \
            unittest.mock.patch.object(WhisperFileTranscriber, 'run') as mock_run:
        # Mock demucs.api.Separator and save_audio
        mock_separator_instance = unittest.mock.Mock()
        mock_separator_instance.separate_audio_file.return_value = (None, {"vocals": "mock_vocals_data"})
        mock_separator_instance.samplerate = 44100
        mock_separator_class.return_value = mock_separator_instance

        mock_run.side_effect = lambda: worker.current_transcriber.completed.emit([
            {"start": 0, "end": 1000, "text": "Test transcription with speech extraction."}
        ])

        completed_spy = unittest.mock.Mock()
        worker.task_completed.connect(completed_spy)
        worker.add_task(task)

        # Wait for the signal to be emitted
        timeout = 10  # seconds
        start_time = time.time()
        while not completed_spy.called and (time.time() - start_time) < timeout:
            QCoreApplication.processEvents()
            time.sleep(0.1)

        mock_separator_class.assert_called_once()
        mock_save_audio.assert_called_once()
        completed_spy.assert_called_once()
        args, kwargs = completed_spy.call_args
        assert args[0] == task
        assert len(args[1]) > 0
        assert args[1][0]["text"] == "Test transcription with speech extraction."