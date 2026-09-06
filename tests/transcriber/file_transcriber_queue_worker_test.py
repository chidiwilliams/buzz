import pytest
import subprocess
import unittest.mock
import uuid
from PyQt6.QtCore import QCoreApplication, QThread
from buzz.file_transcriber_queue_worker import (
    FileTranscriberQueueWorker,
    _probe_audio,
    _speech_extraction_worker,
)
from buzz.model_loader import ModelType, TranscriptionModel, WhisperModelSize
from buzz.transcriber.transcriber import FileTranscriptionTask, TranscriptionOptions, FileTranscriptionOptions, Segment
from buzz.transcriber.whisper_file_transcriber import WhisperFileTranscriber
from tests.audio import test_audio_path, test_multibyte_utf8_audio_path
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

    def test_cancel_force_terminated_current_task_releases_activity(
        self, simple_worker
    ):
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path",
        )
        busy_spy = unittest.mock.Mock()
        simple_worker.queue_busy_changed.connect(busy_spy)
        simple_worker.trigger_run.disconnect(simple_worker.run)
        simple_worker.is_running = True
        simple_worker.add_task(task)
        assert simple_worker._get_next_task()
        simple_worker.current.transcriber = unittest.mock.Mock()
        simple_worker.current.transcriber_thread = unittest.mock.Mock()
        simple_worker.current.transcriber_thread.wait.return_value = False

        simple_worker.cancel_task(task.uid)

        simple_worker.current.transcriber_thread.terminate.assert_called_once_with()
        assert simple_worker.is_running is False
        assert busy_spy.call_args_list == [
            unittest.mock.call(True),
            unittest.mock.call(False),
        ]

    def test_cancel_does_not_terminate_task_that_replaces_current_during_wait(
        self, simple_worker
    ):
        first_task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path",
        )
        second_task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path",
        )
        busy_spy = unittest.mock.Mock()
        simple_worker.queue_busy_changed.connect(busy_spy)
        simple_worker.trigger_run.disconnect(simple_worker.run)
        simple_worker.is_running = True
        simple_worker.add_task(first_task)
        simple_worker.add_task(second_task)
        assert simple_worker._get_next_task()

        first_transcriber = unittest.mock.Mock()
        first_thread = unittest.mock.Mock()
        second_thread = unittest.mock.Mock()
        simple_worker.current.transcriber = first_transcriber
        simple_worker.current.transcriber_thread = first_thread

        def wait_for_first_thread(timeout=None):
            if timeout == 5000:
                assert simple_worker._get_next_task()
                simple_worker.current.transcriber = unittest.mock.Mock()
                simple_worker.current.transcriber_thread = second_thread
                return False
            return True

        first_thread.wait.side_effect = wait_for_first_thread

        simple_worker.cancel_task(first_task.uid)

        first_thread.terminate.assert_called_once_with()
        second_thread.terminate.assert_not_called()
        assert simple_worker.current.task is second_task
        assert simple_worker.is_running is True
        assert busy_spy.call_args_list == [unittest.mock.call(True)]

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
        simple_worker.current.task = task

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
        simple_worker.current.task = task

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
        simple_worker.current.task = task

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

    def test_on_task_completed_with_speech_path(self, simple_worker, tmp_path):
        """Test on_task_completed cleans up speech_path file"""
        options = TranscriptionOptions()
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )
        simple_worker.current.task = task

        # Create a temporary file to simulate speech extraction output
        speech_file = tmp_path / "audio_speech.mp3"
        speech_file.write_bytes(b"fake audio data")
        simple_worker.speech_path = speech_file

        completed_spy = unittest.mock.Mock()
        simple_worker.task_completed.connect(completed_spy)

        simple_worker.on_task_completed([Segment(0, 1000, "Test")])

        completed_spy.assert_called_once()
        # Speech path should be cleaned up
        assert simple_worker.speech_path is None
        assert not speech_file.exists()

    def test_on_task_completed_speech_path_missing(self, simple_worker, tmp_path):
        """Test on_task_completed handles missing speech_path file gracefully"""
        options = TranscriptionOptions()
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )
        simple_worker.current.task = task

        # Set a speech path that doesn't exist
        simple_worker.speech_path = tmp_path / "nonexistent_speech.mp3"

        completed_spy = unittest.mock.Mock()
        simple_worker.task_completed.connect(completed_spy)

        # Should not raise even if file doesn't exist
        simple_worker.on_task_completed([])

        completed_spy.assert_called_once()
        assert simple_worker.speech_path is None

    def test_on_task_download_progress(self, simple_worker):
        """Test on_task_download_progress emits signal"""
        options = TranscriptionOptions()
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )
        simple_worker.current.task = task

        download_spy = unittest.mock.Mock()
        simple_worker.task_download_progress.connect(download_spy)

        simple_worker.on_task_download_progress(0.5)

        download_spy.assert_called_once()
        args = download_spy.call_args[0]
        assert args[0] == task
        assert args[1] == 0.5

    def test_cancel_task_stops_current_transcriber(self, simple_worker):
        """Test cancel_task stops the current transcriber if it matches"""
        options = TranscriptionOptions()
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )
        simple_worker.current.task = task

        mock_transcriber = unittest.mock.Mock()
        simple_worker.current.transcriber = mock_transcriber

        simple_worker.cancel_task(task.uid)

        assert task.uid in simple_worker.canceled_tasks
        mock_transcriber.stop.assert_called_once()

    def test_on_task_error_task_in_canceled_set(self, simple_worker):
        """Test on_task_error does not emit signal when task is canceled"""
        options = TranscriptionOptions()
        task = FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )
        simple_worker.current.task = task
        # Mark task as canceled
        simple_worker.canceled_tasks.add(task.uid)

        error_spy = unittest.mock.Mock()
        simple_worker.task_error.connect(error_spy)

        simple_worker.on_task_error("Some error")

        # Should NOT emit since task was canceled
        error_spy.assert_not_called()


class TestFileTranscriberQueueWorkerRun:
    def _make_task(self, model_type=ModelType.WHISPER_CPP, extract_speech=False):
        options = TranscriptionOptions(
            model=TranscriptionModel(model_type=model_type, whisper_model_size=WhisperModelSize.TINY),
            extract_speech=extract_speech
        )
        return FileTranscriptionTask(
            file_path=str(test_multibyte_utf8_audio_path),
            transcription_options=options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="mock_path"
        )

    def test_run_returns_early_when_already_running(self, simple_worker):
        simple_worker.is_running = True
        # Should return without blocking (queue is empty, no get() call)
        simple_worker.run()
        # is_running stays True, nothing changed
        assert simple_worker.is_running is True

    def test_busy_signal_spans_all_pending_tasks(self, simple_worker):
        first_task = self._make_task()
        second_task = self._make_task()
        busy_spy = unittest.mock.Mock()
        simple_worker.queue_busy_changed.connect(busy_spy)
        simple_worker.trigger_run.disconnect(simple_worker.run)
        simple_worker.is_running = True

        simple_worker.add_task(first_task)
        simple_worker.add_task(second_task)
        assert simple_worker._get_next_task()
        simple_worker._on_task_finished()
        assert simple_worker._get_next_task()
        simple_worker._on_task_finished()

        assert busy_spy.call_args_list == [
            unittest.mock.call(True),
            unittest.mock.call(False),
        ]

    def test_run_stops_on_sentinel(self, simple_worker, qapp):
        completed_spy = unittest.mock.Mock()
        simple_worker.completed.connect(completed_spy)

        simple_worker.tasks_queue.put(None)
        simple_worker.run()

        completed_spy.assert_called_once()
        assert simple_worker.is_running is False

    def test_run_skips_canceled_task_then_stops_on_sentinel(self, simple_worker, qapp):
        task = self._make_task()
        simple_worker.canceled_tasks.add(task.uid)

        started_spy = unittest.mock.Mock()
        simple_worker.task_started.connect(started_spy)

        # Put canceled task then sentinel
        simple_worker.tasks_queue.put(task)
        simple_worker.tasks_queue.put(None)

        simple_worker.run()

        # Canceled task should be skipped; completed emitted
        started_spy.assert_not_called()
        assert simple_worker.is_running is False

    def test_run_creates_openai_transcriber(self, simple_worker, qapp):
        from buzz.transcriber.openai_whisper_api_file_transcriber import OpenAIWhisperAPIFileTranscriber

        task = self._make_task(model_type=ModelType.OPEN_AI_WHISPER_API)
        simple_worker.tasks_queue.put(task)

        with unittest.mock.patch.object(OpenAIWhisperAPIFileTranscriber, 'run'), \
             unittest.mock.patch.object(OpenAIWhisperAPIFileTranscriber, 'moveToThread'), \
             unittest.mock.patch('buzz.file_transcriber_queue_worker.QThread') as mock_thread_class:
            mock_thread = unittest.mock.MagicMock()
            mock_thread_class.return_value = mock_thread

            simple_worker.run()

            assert isinstance(simple_worker.current.transcriber, OpenAIWhisperAPIFileTranscriber)

    def test_run_creates_whisper_transcriber_for_whisper_cpp(self, simple_worker, qapp):
        task = self._make_task(model_type=ModelType.WHISPER_CPP)
        simple_worker.tasks_queue.put(task)

        with unittest.mock.patch.object(WhisperFileTranscriber, 'run'), \
             unittest.mock.patch.object(WhisperFileTranscriber, 'moveToThread'), \
             unittest.mock.patch('buzz.file_transcriber_queue_worker.QThread') as mock_thread_class:
            mock_thread = unittest.mock.MagicMock()
            mock_thread_class.return_value = mock_thread

            simple_worker.run()

            assert isinstance(simple_worker.current.transcriber, WhisperFileTranscriber)

    def test_run_speech_extraction_failure_emits_error(self, simple_worker, qapp):
        task = self._make_task(extract_speech=True)
        simple_worker.trigger_run.disconnect(simple_worker.run)
        simple_worker.is_running = True
        simple_worker.add_task(task)
        simple_worker.is_running = False

        error_spy = unittest.mock.Mock()
        busy_spy = unittest.mock.Mock()
        simple_worker.task_error.connect(error_spy)
        simple_worker.queue_busy_changed.connect(busy_spy)

        with unittest.mock.patch.object(
            FileTranscriberQueueWorker, '_extract_speech', return_value="error"
        ):
            simple_worker.run()

        error_spy.assert_called_once()
        args = error_spy.call_args[0]
        assert args[0] == task
        assert simple_worker.is_running is False
        assert busy_spy.call_args_list == [unittest.mock.call(False)]

    def _run_extract_speech(self, simple_worker, messages, exitcode=0):
        """Drive _extract_speech with a scripted sequence of pipe messages."""
        task = self._make_task(extract_speech=True)
        simple_worker.current.task = task

        recv_conn = unittest.mock.Mock()
        recv_conn.recv.side_effect = list(messages) + [EOFError()]
        send_conn = unittest.mock.Mock()
        process = unittest.mock.Mock()
        process.exitcode = exitcode

        with unittest.mock.patch(
            'buzz.file_transcriber_queue_worker.multiprocessing.Pipe',
            return_value=(recv_conn, send_conn),
        ), unittest.mock.patch(
            'buzz.file_transcriber_queue_worker.multiprocessing.Process',
            return_value=process,
        ):
            status = simple_worker._extract_speech("in.mp3", "out.mp3", "cpu")

        return status, process

    def test_extract_speech_runs_out_of_process_and_returns_ok(self, simple_worker):
        progress_spy = unittest.mock.Mock()
        simple_worker.task_progress.connect(progress_spy)

        status, process = self._run_extract_speech(
            simple_worker,
            [("progress", 50.0, 100.0), ("done", None)],
        )

        assert status == "ok"
        process.start.assert_called_once()
        process.join.assert_called()
        # Progress is forwarded to the UI and the process handle is cleared.
        progress_spy.assert_called_once()
        assert simple_worker.speech_extractor_process is None

    def test_extract_speech_no_audio_stream(self, simple_worker):
        status, _process = self._run_extract_speech(
            simple_worker, [("no_audio", "list index out of range")]
        )
        assert status == "no_audio"

    def test_extract_speech_error_message(self, simple_worker):
        status, _process = self._run_extract_speech(
            simple_worker, [("error", "boom")]
        )
        assert status == "error"

    def test_extract_speech_child_crash_is_error(self, simple_worker):
        # Child exits without reporting a terminal result.
        status, _process = self._run_extract_speech(
            simple_worker, [], exitcode=1
        )
        assert status == "error"


def test_transcription_with_whisper_cpp_tiny_no_speech_extraction(worker):
    options = TranscriptionOptions(
        model=TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY),
        extract_speech=False
    )
    task = FileTranscriptionTask(file_path=str(test_multibyte_utf8_audio_path), transcription_options=options,
                                 file_transcription_options=FileTranscriptionOptions(), model_path="mock_path")

    with unittest.mock.patch.object(WhisperFileTranscriber, 'run') as mock_run:
        mock_run.side_effect = lambda: worker.current.transcriber.completed.emit([
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

    # Speech extraction now runs in a separate process (#1509). Patch the
    # method that manages that process rather than demucs internals, which live
    # in the spawned child and are not reachable from the test process.
    with unittest.mock.patch.object(
            FileTranscriberQueueWorker, '_extract_speech', return_value="ok") as mock_extract, \
            unittest.mock.patch.object(WhisperFileTranscriber, 'run') as mock_run:
        mock_run.side_effect = lambda: worker.current.transcriber.completed.emit([
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

        mock_extract.assert_called_once()
        completed_spy.assert_called_once()
        args, kwargs = completed_spy.call_args
        assert args[0] == task
        assert len(args[1]) > 0
        assert args[1][0]["text"] == "Test transcription with speech extraction."


class _FakeSeparator:
    """Stand-in for demucs that echoes its input back as the vocals stem."""

    samplerate = 44100
    audio_channels = 2

    def __init__(self, device=None, progress=False, callback=None):
        self.callback = callback
        self.window_lengths = []

    def separate_tensor(self, wav, sr):
        self.window_lengths.append(wav.shape[1])
        if self.callback is not None:
            self.callback({"segment_offset": 0, "audio_length": wav.shape[1]})
        return wav, {"vocals": wav}


class TestSpeechExtractionWorker:
    @pytest.fixture
    def fake_separator(self):
        separators = []

        def make(**kwargs):
            separator = _FakeSeparator(**kwargs)
            separators.append(separator)
            return separator

        with unittest.mock.patch(
            "buzz.file_transcriber_queue_worker.demucsApi.Separator", side_effect=make
        ):
            yield separators

    @staticmethod
    def _run(file_path, speech_path):
        conn = unittest.mock.Mock()
        messages = []
        conn.send.side_effect = messages.append
        _speech_extraction_worker(conn, str(file_path), str(speech_path), "cpu")
        return messages

    @staticmethod
    def _duration(file_path):
        return _probe_audio(str(file_path))[1]

    def test_extracts_whole_file_in_bounded_windows(
        self, fake_separator, tmp_path, monkeypatch
    ):
        # A window shorter than the test audio, so several windows are needed.
        monkeypatch.setattr(
            "buzz.file_transcriber_queue_worker._EXTRACTION_WINDOW_SECONDS", 2
        )
        monkeypatch.setattr(
            "buzz.file_transcriber_queue_worker._EXTRACTION_CONTEXT_SECONDS", 1
        )
        speech_path = tmp_path / "speech.mp3"

        messages = self._run(test_audio_path, speech_path)

        assert ("done", None) in messages
        assert speech_path.exists()
        # Separation never sees more than one window plus its context, however
        # long the file is.
        separator = fake_separator[0]
        assert len(separator.window_lengths) > 1
        assert max(separator.window_lengths) <= 4 * separator.samplerate
        # The whole file still made it into the output.
        assert self._duration(speech_path) == pytest.approx(
            self._duration(test_audio_path), abs=0.5
        )

    def test_single_window_covers_short_file(self, fake_separator, tmp_path):
        speech_path = tmp_path / "speech.mp3"

        messages = self._run(test_audio_path, speech_path)

        assert ("done", None) in messages
        assert len(fake_separator[0].window_lengths) == 1
        assert self._duration(speech_path) == pytest.approx(
            self._duration(test_audio_path), abs=0.5
        )

    def test_progress_is_reported_against_the_whole_file(
        self, fake_separator, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "buzz.file_transcriber_queue_worker._EXTRACTION_WINDOW_SECONDS", 2
        )
        monkeypatch.setattr(
            "buzz.file_transcriber_queue_worker._EXTRACTION_CONTEXT_SECONDS", 1
        )

        messages = self._run(test_audio_path, tmp_path / "speech.mp3")

        progress = [message for message in messages if message[0] == "progress"]
        assert len(progress) > 1
        offsets = [message[1] for message in progress]
        # Offsets advance through the file rather than restarting per window.
        assert offsets == sorted(offsets)
        assert offsets[-1] > offsets[0]
        total_frames = progress[0][2]
        assert total_frames == pytest.approx(
            self._duration(test_audio_path) * 44100, rel=0.01
        )
        assert offsets[-1] <= total_frames

    def test_video_without_audio_reports_no_audio(self, fake_separator, tmp_path):
        video_path = tmp_path / "silent.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "color=c=black:s=64x64:d=1", str(video_path)],
            check=True,
        )
        speech_path = tmp_path / "speech.mp3"

        messages = self._run(video_path, speech_path)

        assert messages[0][0] == "no_audio"
        assert not speech_path.exists()

    def test_unreadable_file_reports_error(self, fake_separator, tmp_path):
        broken_path = tmp_path / "broken.mp3"
        broken_path.write_bytes(b"not audio")
        speech_path = tmp_path / "speech.mp3"

        messages = self._run(broken_path, speech_path)

        assert messages[0][0] == "error"
        # No half-written file is left behind for the transcriber to pick up.
        assert not speech_path.exists()
