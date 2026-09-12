from unittest.mock import Mock, patch

from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.speaker_identifier import (
    build_speaker_segments,
    identify_speakers,
)
from buzz.transcriber.transcriber import (
    FileTranscriptionOptions,
    FileTranscriptionTask,
    Segment,
    TranscriptionOptions,
)


IDENTIFICATION_RESULT = [
    {"start_time": 0, "end_time": 100, "text": "Hello.", "speaker": "Speaker 0"},
    {"start_time": 100, "end_time": 200, "text": "How are you?", "speaker": "Speaker 0"},
    {"start_time": 200, "end_time": 300, "text": "Good.", "speaker": "Speaker 1"},
]


class TestBuildSpeakerSegments:
    def test_merges_adjacent_segments_of_the_same_speaker(self):
        segments = build_speaker_segments(IDENTIFICATION_RESULT)

        assert segments == [
            Segment(0, 200, "Hello. How are you?", speaker="Speaker 0"),
            Segment(200, 300, "Good.", speaker="Speaker 1"),
        ]

    def test_keeps_segments_separate_when_not_merging(self):
        segments = build_speaker_segments(
            IDENTIFICATION_RESULT, merge_speaker_sentences=False
        )

        assert [segment.text for segment in segments] == [
            "Hello.",
            "How are you?",
            "Good.",
        ]

    def test_applies_speaker_mapping(self):
        segments = build_speaker_segments(
            IDENTIFICATION_RESULT, speaker_mapping={"Speaker 0": "Alice"}
        )

        assert [segment.speaker for segment in segments] == ["Alice", "Speaker 1"]


class TestIdentifySpeakers:
    def run_with_worker(self, worker_run, segments, **kwargs):
        worker = Mock()
        worker.run.side_effect = lambda: worker_run(worker)

        with patch(
            "buzz.widgets.transcription_viewer.speaker_identification_widget"
            ".IdentificationWorker",
            return_value=worker,
        ) as worker_class:
            result = identify_speakers(
                file_path="audio.mp3", segments=segments, **kwargs
            )

        return result, worker_class, worker

    def test_labels_segments_with_identified_speakers(self):
        segments = [Segment(0, 300, "Hello. How are you? Good.")]

        def worker_run(worker):
            worker.finished.connect.call_args[0][0](IDENTIFICATION_RESULT)

        result, worker_class, _worker = self.run_with_worker(
            worker_run, segments, language="en", diarizer="msdd", num_speakers=2
        )

        assert [(segment.speaker, segment.text) for segment in result] == [
            ("Speaker 0", "Hello. How are you?"),
            ("Speaker 1", "Good."),
        ]

        kwargs = worker_class.call_args.kwargs
        assert kwargs["segments"] == segments
        assert kwargs["file_path"] == "audio.mp3"
        assert kwargs["language"] == "en"
        assert kwargs["diarizer"] == "msdd"
        assert kwargs["num_speakers"] == 2

    def test_ignores_speaker_count_for_sortformer(self):
        def worker_run(worker):
            worker.finished.connect.call_args[0][0](IDENTIFICATION_RESULT)

        _result, worker_class, _worker = self.run_with_worker(
            worker_run, [Segment(0, 300, "Hello.")], diarizer="sortformer",
            num_speakers=2,
        )

        assert worker_class.call_args.kwargs["num_speakers"] is None

    def test_returns_original_segments_on_error(self):
        segments = [Segment(0, 300, "Hello.")]

        def worker_run(worker):
            worker.error.connect.call_args[0][0]("boom")
            worker.finished.connect.call_args[0][0]([])

        result, _worker_class, _worker = self.run_with_worker(worker_run, segments)

        assert result == segments

    def test_returns_original_segments_when_worker_raises(self):
        segments = [Segment(0, 300, "Hello.")]

        def worker_run(_worker):
            raise RuntimeError("boom")

        result, _worker_class, _worker = self.run_with_worker(worker_run, segments)

        assert result == segments

    def test_skips_identification_without_segments(self):
        assert identify_speakers(file_path="audio.mp3", segments=[]) == []


class SpeakerFileTranscriber(FileTranscriber):
    def transcribe(self):
        return [Segment(0, 300, " Hello. How are you? Good. ")]

    def stop(self):
        pass


class TestFileTranscriberSpeakerIdentification:
    def make_task(self, identify_speakers: bool) -> FileTranscriptionTask:
        return FileTranscriptionTask(
            transcription_options=TranscriptionOptions(language="en"),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="",
            file_path="audio.mp3",
            identify_speakers=identify_speakers,
            speaker_count=2,
        )

    def test_identifies_speakers_before_completing(self):
        transcriber = SpeakerFileTranscriber(self.make_task(identify_speakers=True))

        labeled = [Segment(0, 300, "Hello.", speaker="Speaker 0")]
        completed = Mock()
        transcriber.completed.connect(completed)

        with patch(
            "buzz.transcriber.speaker_identifier.identify_speakers",
            return_value=labeled,
        ) as mock_identify:
            transcriber.run()

        mock_identify.assert_called_once()
        assert mock_identify.call_args.kwargs["file_path"] == "audio.mp3"
        assert mock_identify.call_args.kwargs["language"] == "en"
        assert mock_identify.call_args.kwargs["num_speakers"] == 2
        # Segments are stripped before identification runs
        assert mock_identify.call_args.kwargs["segments"] == [
            Segment(0, 300, "Hello. How are you? Good.")
        ]
        assert completed.call_args[0][0] == labeled

    def test_does_not_identify_speakers_when_disabled(self):
        transcriber = SpeakerFileTranscriber(self.make_task(identify_speakers=False))

        with patch(
            "buzz.transcriber.speaker_identifier.identify_speakers"
        ) as mock_identify:
            transcriber.run()

        mock_identify.assert_not_called()
