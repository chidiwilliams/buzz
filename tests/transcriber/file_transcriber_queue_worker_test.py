import pytest
import unittest.mock
from PyQt6.QtCore import QCoreApplication, QThread
from buzz.file_transcriber_queue_worker import FileTranscriberQueueWorker
from buzz.model_loader import ModelType, TranscriptionModel
from buzz.transcriber.transcriber import FileTranscriptionTask, TranscriptionOptions, FileTranscriptionOptions
from buzz.transcriber.whisper_cpp_file_transcriber import WhisperCppFileTranscriber
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
def audio_file():
    # Use a small, existing audio file for testing
    return test_multibyte_utf8_audio_path

def test_transcription_with_whisper_cpp_tiny_no_speech_extraction(worker, audio_file):
    options = TranscriptionOptions(
        model=TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size="tiny"),
        extract_speech=False
    )
    task = FileTranscriptionTask(file_path=str(audio_file), transcription_options=options, file_transcription_options=FileTranscriptionOptions(), model_path="mock_path")

    with unittest.mock.patch.object(WhisperCppFileTranscriber, 'run') as mock_run:
        mock_run.side_effect = lambda: worker.current_transcriber.completed.emit([
            {"start": 0, "end": 1000, "text": "Test transcription."}
        ])
        
        completed_spy = unittest.mock.Mock()
        worker.task_completed.connect(completed_spy)
        worker.add_task(task)

        # Wait for the signal to be emitted
        timeout = 5  # seconds
        start_time = time.time()
        while not completed_spy.called and (time.time() - start_time) < timeout:
            QCoreApplication.processEvents()
            time.sleep(0.1)

        completed_spy.assert_called_once()
        args, kwargs = completed_spy.call_args
        assert args[0] == task
        assert len(args[1]) > 0
        assert args[1][0]["text"] == "Test transcription."

def test_transcription_with_whisper_cpp_tiny_with_speech_extraction(worker, audio_file):
    options = TranscriptionOptions(
        model=TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size="tiny"),
        extract_speech=True
    )
    task = FileTranscriptionTask(file_path=str(audio_file), transcription_options=options, file_transcription_options=FileTranscriptionOptions(), model_path="mock_path")

    with unittest.mock.patch('demucs.api.Separator') as mock_separator_class, \
         unittest.mock.patch('demucs.api.save_audio') as mock_save_audio, \
         unittest.mock.patch.object(WhisperCppFileTranscriber, 'run') as mock_run:

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
        timeout = 5  # seconds
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
