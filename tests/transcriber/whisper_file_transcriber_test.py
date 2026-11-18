import glob
import logging
import multiprocessing
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from threading import Thread
from typing import List
from unittest.mock import Mock, patch

import psutil
import pytest
from pytestqt.qtbot import QtBot

from buzz import metadata_cache
from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import (
    OutputFormat,
    get_output_file_path,
    FileTranscriptionTask,
    TranscriptionOptions,
    Task,
    FileTranscriptionOptions,
    Segment,
)
from buzz.transcriber.whisper_file_transcriber import (
    WhisperFileTranscriber,
    check_file_has_audio_stream,
    terminate_child_processes,
    PROGRESS_REGEX,
)
from tests.audio import test_audio_path
from tests.model_loader import get_model_path

MODULE = "buzz.transcriber.whisper_file_transcriber"


def _spawn_grandchild_worker(pipe):
    """Multiprocessing target that mirrors the whisper.cpp process tree.

    Spawns a long-lived subprocess (the stand-in for ``whisper-cli``), reports
    its pid back to the parent, then blocks waiting on it. This gives us a
    three-level tree (test -> worker process -> subprocess) to verify that
    ``terminate_child_processes`` reaps grandchildren, not just the direct child.
    """
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    pipe.send(proc.pid)
    pipe.close()
    proc.wait()


def _is_dead_or_zombie(proc: psutil.Process) -> bool:
    """True if the process is gone, or a not-yet-reaped zombie."""
    try:
        if not proc.is_running():
            return True
        return proc.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def _wait_until(predicate, timeout: float = 15.0, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class TestCheckFileHasAudioStream:
    def test_valid_audio_file(self):
        # Should not raise exception for valid audio file
        check_file_has_audio_stream(test_audio_path)

    def test_missing_file(self):
        with pytest.raises(ValueError, match="File not found"):
            check_file_has_audio_stream("/nonexistent/path/to/file.mp3")

    def test_invalid_media_file(self):
        # Create a temporary text file (not a valid media file)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        try:
            temp_file.write(b"This is not a valid media file")
            temp_file.close()
            with pytest.raises(ValueError, match="Invalid media file"):
                check_file_has_audio_stream(temp_file.name)
        finally:
            os.unlink(temp_file.name)


class TestProgressRegex:
    def test_integer_percentage(self):
        match = PROGRESS_REGEX.search("Progress: 50%")
        assert match is not None
        assert match.group() == "50%"

    def test_decimal_percentage(self):
        match = PROGRESS_REGEX.search("Progress: 75.5%")
        assert match is not None
        assert match.group() == "75.5%"

    def test_no_match(self):
        match = PROGRESS_REGEX.search("No percentage here")
        assert match is None

    def test_extract_percentage_value(self):
        line = "Transcription progress: 85%"
        match = PROGRESS_REGEX.search(line)
        assert match is not None
        percentage = int(match.group().strip("%"))
        assert percentage == 85


class TestTerminateChildProcesses:
    def test_kills_grandchild_subprocess(self):
        """The whisper-cli stand-in (a grandchild) must be killed, not orphaned.

        Reproduces the whisper.cpp shape: a multiprocessing worker that spawns
        a long-lived subprocess. terminate_child_processes must kill that
        subprocess while leaving the worker for its owner to reap.
        """
        recv_pipe, send_pipe = multiprocessing.Pipe(duplex=False)
        worker = multiprocessing.Process(
            target=_spawn_grandchild_worker, args=(send_pipe,)
        )
        worker.start()
        # Parent doesn't send; close its copy so the pipe isn't kept open.
        send_pipe.close()

        # The worker reports the grandchild pid once the subprocess is up.
        grandchild_pid = recv_pipe.recv()
        recv_pipe.close()

        worker_proc = psutil.Process(worker.pid)
        grandchild_proc = psutil.Process(grandchild_pid)
        assert worker_proc.is_running()
        assert grandchild_proc.is_running()
        # Sanity check the tree is actually nested two levels deep.
        assert grandchild_pid in {
            child.pid for child in worker_proc.children(recursive=True)
        }

        terminate_child_processes(worker.pid)

        # The grandchild must be gone...
        assert _wait_until(lambda: _is_dead_or_zombie(grandchild_proc)), (
            "whisper-cli stand-in subprocess was orphaned instead of killed"
        )

        # ...and the worker must still be reapable via multiprocessing (i.e.
        # terminate_child_processes must not have stolen its waitpid()).
        worker.terminate()
        worker.join(timeout=10)
        assert not worker.is_alive()

    def test_missing_pid_is_noop(self):
        # A pid that cannot be a live process must not raise.
        terminate_child_processes(-1)


class TestWhisperFileTranscriber:
    @pytest.mark.parametrize(
        "file_path,output_format,expected_file_path",
        [
            pytest.param(
                "/a/b/c.mp4",
                OutputFormat.SRT,
                "/a/b/c-translate--OpenAI Whisper-tiny.srt",
                marks=pytest.mark.skipif(platform.system() == "Windows", reason=""),
            ),
            pytest.param(
                "C:\\a\\b\\c.mp4",
                OutputFormat.SRT,
                "C:\\a\\b\\c-translate--OpenAI Whisper-tiny.srt",
                marks=pytest.mark.skipif(platform.system() != "Windows", reason=""),
            ),
        ],
    )
    def test_default_output_file(
        self,
        file_path: str,
        output_format: OutputFormat,
        expected_file_path: str,
    ):
        file_path = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=output_format,
            output_directory="",
            export_file_name_template="{{ input_file_name }}-{{ task }}-{{ language }}-{{ model_type }}-{{ model_size }}",
        )
        assert file_path == expected_file_path

    @pytest.mark.parametrize(
        "file_path,expected_starts_with",
        [
            pytest.param(
                "/a/b/c.mp4",
                "/a/b/c (Translated on ",
                marks=pytest.mark.skipif(platform.system() == "Windows", reason=""),
            ),
            pytest.param(
                "C:\\a\\b\\c.mp4",
                "C:\\a\\b\\c (Translated on ",
                marks=pytest.mark.skipif(platform.system() != "Windows", reason=""),
            ),
        ],
    )
    def test_default_output_file_with_date(
        self, file_path: str, expected_starts_with: str
    ):
        export_file_name_template = (
            "{{ input_file_name }} (Translated on {{ date_time }})"
        )
        srt = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=OutputFormat.TXT,
            output_directory="",
            export_file_name_template=export_file_name_template,
        )

        assert srt.startswith(expected_starts_with)
        assert srt.endswith(".txt")

        srt = get_output_file_path(
            file_path=file_path,
            language=None,
            task=Task.TRANSLATE,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER,
                whisper_model_size=WhisperModelSize.TINY,
            ),
            output_format=OutputFormat.SRT,
            output_directory="",
            export_file_name_template=export_file_name_template,
        )
        assert srt.startswith(expected_starts_with)
        assert srt.endswith(".srt")

    @pytest.mark.parametrize(
        "word_level_timings,extract_speech,expected_segments,model",
        [
            (
                False,
                False,
                [
                    Segment(
                        0,
                        8400,
                        " Bienvenue dans Passe-Relle. Un podcast pensé pour évêiller",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            (
                True,
                True,
                [Segment(40, 299, " Bien"), Segment(299, 329, "venue dans")],
                TranscriptionModel(
                    model_type=ModelType.WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            (
                False,
                False,
                [
                    Segment(
                        0,
                        8517,
                        " Bienvenue dans Passe-Relle. Un podcast pensé pour évêyer la curiosité des apprenances "
                        "et des apprenances de français.",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.HUGGING_FACE,
                    hugging_face_model_id="openai/whisper-tiny",
                ),
            ),
            pytest.param(
                False,
                False,
                [
                    Segment(
                        start=0,
                        end=8400,
                        text=" Bienvenue dans Passrel, un podcast pensé pour éveiller la curiosité des apprenances et des apprenances de français.",
                    )
                ],
                TranscriptionModel(
                    model_type=ModelType.FASTER_WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
                marks=pytest.mark.skipif(
                    platform.system() == "Darwin" and platform.machine() == "x86_64",
                    reason="Error with libiomp5 already initialized on GH action runner: https://github.com/chidiwilliams/buzz/actions/runs/4657331262/jobs/8241832087",
                ),
            ),
        ],
    )
    def test_transcribe_from_file(
        self,
        qtbot: QtBot,
        word_level_timings: bool,
        extract_speech: bool,
        expected_segments: List[Segment],
        model: TranscriptionModel,
    ):
        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=word_level_timings,
            extract_speech=extract_speech,
            model=model,
        )
        model_path = get_model_path(transcription_options.model)
        file_path = os.path.abspath(test_audio_path)
        file_transcription_options = FileTranscriptionOptions(file_paths=[file_path])

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=file_path,
                model_path=model_path,
            )
        )
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.wait_signal(
            transcriber.progress, timeout=10 * 6000
        ), qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        # Reports progress at 0, 0 <= progress <= 100, and 100
        assert mock_progress.call_count >= 2
        assert mock_progress.call_args_list[0][0][0] == (0, 100)

        mock_completed.assert_called()
        segments = mock_completed.call_args[0][0]
        assert len(segments) >= 0
        for i, expected_segment in enumerate(segments):
            assert segments[i].start >= 0
            assert segments[i].end > 0
            assert len(segments[i].text) > 0
            logging.debug(f"{segments[i].start} {segments[i].end} {segments[i].text}")

        transcriber.stop()
        time.sleep(3)

    def test_transcribe_from_url(self, qtbot):
        url = (
            "https://github.com/chidiwilliams/buzz/raw/main/testdata/whisper-french.mp3"
        )

        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = TranscriptionOptions()
        model_path = get_model_path(transcription_options.model)
        file_transcription_options = FileTranscriptionOptions(url=url)

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                model_path=model_path,
                url=url,
                source=FileTranscriptionTask.Source.URL_IMPORT,
            )
        )
        # The queue worker downloads URL audio before transcribing it.
        transcriber.download()
        assert os.path.isfile(transcriber.transcription_task.file_path)

        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.wait_signal(
            transcriber.progress, timeout=10 * 6000
        ), qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        # Reports progress at 0, 0 <= progress <= 100, and 100
        assert mock_progress.call_count >= 2
        assert mock_progress.call_args_list[0][0][0] == (0, 100)

        mock_completed.assert_called()
        segments = mock_completed.call_args[0][0]
        assert len(segments) >= 0
        for i, expected_segment in enumerate(segments):
            assert segments[i].start >= 0
            assert segments[i].end > 0
            assert len(segments[i].text) > 0
            logging.debug(f"{segments[i].start} {segments[i].end} {segments[i].text}")

        transcriber.stop()
        time.sleep(3)

    def test_transcribe_from_folder_watch_source(self, qtbot):
        file_path = tempfile.mktemp(suffix=".mp3")
        shutil.copy(test_audio_path, file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[file_path],
            output_formats={OutputFormat.TXT},
        )
        transcription_options = TranscriptionOptions()
        model_path = get_model_path(transcription_options.model)

        output_directory = tempfile.mkdtemp()
        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                model_path=model_path,
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=file_path,
                output_directory=output_directory,
                source=FileTranscriptionTask.Source.FOLDER_WATCH,
            )
        )
        with qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        assert not os.path.isfile(file_path)
        assert os.path.isfile(
            os.path.join(output_directory, os.path.basename(file_path))
        )
        assert len(glob.glob("*.txt", root_dir=output_directory)) > 0

        transcriber.stop()
        time.sleep(3)

    def test_transcribe_from_folder_watch_source_deletes_file(self, qtbot):
        file_path = tempfile.mktemp(suffix=".mp3")
        shutil.copy(test_audio_path, file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[file_path],
            output_formats={OutputFormat.TXT},
        )
        transcription_options = TranscriptionOptions()
        model_path = get_model_path(transcription_options.model)

        output_directory = tempfile.mkdtemp()
        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                model_path=model_path,
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=file_path,
                original_file_path=file_path,
                output_directory=output_directory,
                source=FileTranscriptionTask.Source.FOLDER_WATCH,
                delete_source_file=True,
            )
        )
        with qtbot.wait_signal(transcriber.completed, timeout=10 * 6000):
            transcriber.run()

        assert not os.path.isfile(file_path)
        assert not os.path.isfile(
            os.path.join(output_directory, os.path.basename(file_path))
        )
        assert len(glob.glob("*.txt", root_dir=output_directory)) > 0

        transcriber.stop()
        time.sleep(3)

    def test_transcribe_stop(self):
        output_file_path = os.path.join(tempfile.gettempdir(), "whisper.txt")
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=[test_audio_path]
        )
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=False,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )
        model_path = get_model_path(transcription_options.model)

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(
                model_path=model_path,
                transcription_options=transcription_options,
                file_transcription_options=file_transcription_options,
                file_path=test_audio_path,
            )
        )

        # run() blocks until transcription finishes, so drive it from a thread
        # and stop it mid-flight from the test thread.
        run_thread = Thread(target=transcriber.run, daemon=True)
        run_thread.start()

        # Wait until the whisper.cpp worker process AND its whisper-cli
        # subprocess (grandchild) are actually up.
        def worker_tree_is_up() -> bool:
            if not transcriber.started_process:
                return False
            pid = transcriber.current_process.pid
            if pid is None:
                return False
            try:
                return len(psutil.Process(pid).children(recursive=True)) > 0
            except psutil.NoSuchProcess:
                return False

        assert _wait_until(worker_tree_is_up, timeout=60), (
            "whisper.cpp worker/subprocess did not start"
        )

        worker_pid = transcriber.current_process.pid
        worker_proc = psutil.Process(worker_pid)
        descendants = worker_proc.children(recursive=True)
        assert descendants, "whisper-cli subprocess did not start"

        transcriber.stop()

        # run() must return promptly and the whole process tree must be gone.
        run_thread.join(timeout=30)
        assert not run_thread.is_alive(), "transcriber.run() did not return after stop()"

        assert _wait_until(lambda: _is_dead_or_zombie(worker_proc))
        for child in descendants:
            assert _wait_until(lambda child=child: _is_dead_or_zombie(child)), (
                f"whisper-cli subprocess {child.pid} still running after stop()"
            )

        # Assert that file was not created
        assert os.path.isfile(output_file_path) is False


class TestTranscribeFasterWhisper:
    def test_raises_when_model_path_is_empty(self):
        task = FileTranscriptionTask(
            model_path="",
            transcription_options=TranscriptionOptions(
                model=TranscriptionModel(
                    model_type=ModelType.FASTER_WHISPER,
                    whisper_model_size=WhisperModelSize.TINY,
                )
            ),
            file_transcription_options=FileTranscriptionOptions(file_paths=[test_audio_path]),
            file_path=test_audio_path,
        )
        with pytest.raises(FileNotFoundError, match="BUZZ_MODEL_ROOT"):
            WhisperFileTranscriber.transcribe_faster_whisper(task)

        time.sleep(3)

class _FakeTerminatedProcess:
    """Stands in for the whisper worker killed by a signal."""

    def __init__(self, exitcode: int):
        self.exitcode = exitcode
        self.pid = os.getpid()

    def start(self):
        pass

    def join(self, timeout=None):
        pass

    def terminate(self):
        pass


@pytest.mark.parametrize(
    "exitcode",
    [
        -15,  # SIGTERM, what multiprocessing reports when the app closes
        -9,  # SIGKILL
        -2,  # SIGINT
        143,  # 128 + SIGTERM, shell-style
    ],
)
def test_transcribe_reports_terminated_process_as_canceled(monkeypatch, exitcode):
    task = FileTranscriptionTask(
        model_path="",
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(
            file_paths=[test_audio_path]
        ),
        file_path=test_audio_path,
    )
    transcriber = WhisperFileTranscriber(task=task)

    monkeypatch.setattr(
        "buzz.transcriber.whisper_file_transcriber.multiprocessing.Process",
        lambda target, args: _FakeTerminatedProcess(exitcode),
    )

    with pytest.raises(Exception, match="Transcription was canceled"):
        transcriber.transcribe()


class TestTranscriberMetadata:
    """Each engine keeps its full result in the metadata cache of the task."""

    def make_task(self, model_type, word_level_timings=False):
        return FileTranscriptionTask(
            model_path="/fake/model",
            transcription_options=TranscriptionOptions(
                language="en",
                word_level_timings=word_level_timings,
                model=TranscriptionModel(
                    model_type=model_type, whisper_model_size=WhisperModelSize.TINY
                ),
            ),
            file_transcription_options=FileTranscriptionOptions(file_paths=[test_audio_path]),
            file_path=test_audio_path,
        )

    def test_faster_whisper(self, metadata_dir):
        from faster_whisper.transcribe import Segment as FasterSegment
        from faster_whisper.transcribe import TranscriptionInfo, Word

        task = self.make_task(ModelType.FASTER_WHISPER, word_level_timings=True)
        whisper_segment = FasterSegment(
            id=1, seek=0, start=0.0, end=1.5, text=" Hello there", tokens=[50364, 2425],
            avg_logprob=-0.25, compression_ratio=1.1, no_speech_prob=0.02,
            words=[
                Word(start=0.0, end=0.5, word=" Hello", probability=0.98),
                Word(start=0.5, end=1.5, word=" there", probability=0.61),
            ],
            temperature=0.0,
        )
        info = TranscriptionInfo(
            language="en", language_probability=0.97, duration=1.5,
            duration_after_vad=1.5, all_language_probs=[("en", 0.97)],
            transcription_options=None, vad_options=None,
        )
        pipeline = Mock()
        # A generator, like the real pipeline, so it can only be read once
        pipeline.transcribe.return_value = ((s for s in [whisper_segment]), info)

        with patch(f"{MODULE}.faster_whisper.WhisperModel"), patch(
            f"{MODULE}.faster_whisper.BatchedInferencePipeline", return_value=pipeline
        ), patch(f"{MODULE}.whisper_audio.load_audio"), patch(
            f"{MODULE}.cuda_works", return_value=False
        ):
            segments = WhisperFileTranscriber.transcribe_faster_whisper(task)

        assert [segment.text for segment in segments] == [" Hello", " there"]
        metadata = metadata_cache.load_metadata(task.uid, metadata_cache.FASTER_WHISPER)
        assert metadata["info"]["language_probability"] == 0.97
        saved_segment = metadata["segments"][0]
        assert saved_segment["no_speech_prob"] == 0.02
        assert saved_segment["avg_logprob"] == -0.25
        assert saved_segment["words"][1] == {
            "start": 0.5, "end": 1.5, "word": " there", "probability": 0.61,
        }

    def test_openai_whisper(self, metadata_dir):
        task = self.make_task(ModelType.WHISPER)
        result = {
            "text": " Hello",
            "language": "en",
            "segments": [{
                "id": 0, "start": 0.0, "end": 1.5, "text": " Hello", "tokens": [2425],
                "avg_logprob": -0.3, "compression_ratio": 0.8, "no_speech_prob": 0.04,
                "temperature": 0.0,
            }],
        }
        model = Mock()
        model.transcribe.return_value = result

        with patch(f"{MODULE}.whisper.load_model", return_value=model), patch(
            f"{MODULE}.whisper_audio.load_audio"
        ), patch(f"{MODULE}.cuda_works", return_value=False):
            segments = WhisperFileTranscriber.transcribe_openai_whisper(task)

        assert [segment.text for segment in segments] == [" Hello"]
        assert metadata_cache.load_metadata(task.uid, metadata_cache.OPENAI_WHISPER) == result

    def test_openai_whisper_word_level_timings(self, metadata_dir):
        task = self.make_task(ModelType.WHISPER, word_level_timings=True)
        result = Mock()
        result.segments = []
        result.to_dict.return_value = {"segments": [{"avg_logprob": -0.3, "words": []}]}
        model = Mock()
        model.transcribe.return_value = result

        with patch(f"{MODULE}.whisper.load_model", return_value=model), patch(
            f"{MODULE}.stable_whisper.modify_model"
        ), patch(f"{MODULE}.whisper_audio.load_audio"), patch(
            f"{MODULE}.cuda_works", return_value=False
        ):
            WhisperFileTranscriber.transcribe_openai_whisper(task)

        assert metadata_cache.load_metadata(task.uid, metadata_cache.OPENAI_WHISPER) == {
            "segments": [{"avg_logprob": -0.3, "words": []}]
        }

    def test_hugging_face(self, metadata_dir):
        task = self.make_task(ModelType.HUGGING_FACE)
        result = {
            "text": "Hello",
            "segments": [{"start": 0.0, "end": 1.5, "text": "Hello", "score": 0.9}],
        }
        model = Mock(is_mms_model=False)
        model.transcribe.return_value = result

        with patch(f"{MODULE}.TransformersTranscriber", return_value=model):
            segments = WhisperFileTranscriber.transcribe_hugging_face(task)

        assert [segment.text for segment in segments] == ["Hello"]
        assert metadata_cache.load_metadata(task.uid, metadata_cache.HUGGING_FACE) == result
