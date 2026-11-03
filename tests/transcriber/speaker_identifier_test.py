import platform
import unicodedata
from unittest.mock import MagicMock, Mock, patch

import pytest
import torch

from buzz.transcriber import speaker_identifier
from buzz.transcriber.file_transcriber import FileTranscriber
from buzz.transcriber.speaker_identifier import (
    ALIGNMENT_CHUNK_MAX_REACH_BACK_MS,
    ALIGNMENT_CHUNK_PADDING_MS,
    ALIGNMENT_MAX_WORD_CHARS,
    AlignmentFailedError,
    TranscriptAligner,
    build_alignment_chunks,
    build_speaker_segments,
    clamp_chunk_words,
    identify_speakers,
    split_long_words,
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


def make_aligner(**kwargs):
    """An aligner whose tests replace the parts they need."""
    defaults = dict(
        preprocess_text=MagicMock(),
        get_alignments=MagicMock(),
        get_spans=MagicMock(),
        postprocess_results=MagicMock(),
        langs_to_iso={"en": "eng", "ja": "jpn"},
    )
    return TranscriptAligner(**{**defaults, **kwargs})


def ten_minutes_of_emissions(stride=20.0):
    return torch.zeros(int(10 * 60 * 1000 / stride), 4)


class TestBuildAlignmentChunks:
    def test_groups_segments(self):
        segments = [
            Segment(4000, 6000, "three"),
            Segment(0, 2000, "one  "),
            Segment(2000, 4000, "two"),
            Segment(6000, 8000, "  "),
            Segment(9000, 10000, " "),
        ]

        chunks = build_alignment_chunks(segments, chunk_duration_ms=4000)

        # Sorted by time, whitespace collapsed, text-less window dropped
        assert chunks == [("one two", 0, 4000), ("three", 4000, 8000)]

    def test_keeps_order_of_segments_starting_together(self):
        chunks = build_alignment_chunks(
            [Segment(1000, 3000, "first"), Segment(1000, 2000, "second")],
        )

        assert chunks == [("first second", 1000, 3000)]

    def test_long_segment_gets_a_window_of_its_own(self):
        chunks = build_alignment_chunks(
            [Segment(0, 1000, "a"), Segment(1000, 601000, "long"), Segment(601000, 602000, "b")],
        )

        assert chunks == [("a", 0, 1000), ("long", 1000, 601000), ("b", 601000, 602000)]


def test_clamp_chunk_words_reconciles_starts_and_audio_bounds():
    words = [
        {"start": -1, "end": 10},
        {"start": 2, "end": 5},
        {"start": 1, "end": 3},
        {"start": 20, "end": 30},
    ]
    clamp_chunk_words(words, 8)
    assert [(word["start"], word["end"]) for word in words] == [(0, 2), (2, 2), (2, 3), (8, 8)]


def test_split_long_words_keeps_marks_with_their_consonant():
    phrase = "สวัสดีครับวันนี้อากาศดีมากเลยนะครับ"  # Thai, no spaces
    pieces, joins = split_long_words(f"{phrase} hello")

    assert len(pieces) == 3
    assert "".join(pieces[:2]) == phrase
    assert pieces[2] == "hello"
    assert joins == [False, True, False]
    assert all(len(piece) <= 24 for piece in pieces)
    assert not any(unicodedata.category(piece[0]).startswith("M") for piece in pieces)


def test_split_long_words_keeps_leading_vowels_with_their_consonant():
    # Thai writes these vowels before the consonant they follow, and uroman
    # reorders them: "เป็น" romanizes to "pen", but "เ" + "ป็น" to "e" + "pon"
    word = "ก" * 23 + "เป็น" + "ก" * 20
    pieces, _joins = split_long_words(word)

    assert "".join(pieces) == word
    assert len(pieces) == 2
    assert not any(piece[-1] in "เแโใไ" for piece in pieces)


def test_split_long_words_pieces_are_not_split_again():
    """Overlap re-alignment splits its contested pieces again, which must keep them."""
    word = "ก" * 24 + "่" + "ก" * 23  # a tone mark right where the split falls
    pieces, _joins = split_long_words(word)

    assert "".join(pieces) == word
    assert all(len(piece) <= ALIGNMENT_MAX_WORD_CHARS for piece in pieces)
    assert split_long_words(" ".join(pieces))[0] == pieces


class TestTranscriptAligner:
    @pytest.mark.parametrize("transcript", ["", "  "])
    def test_empty_transcript_of_long_audio_gets_the_aligner_error(self, transcript):
        aligner = make_aligner()
        aligner._align_text = MagicMock(side_effect=AssertionError("Empty transcript"))

        with pytest.raises(AssertionError, match="Empty transcript"):
            aligner.align(
                transcript, "en", ten_minutes_of_emissions(), 20.0, "tokenizer",
                segments=[Segment(0, 1000, transcript)],
            )

    def test_short_transcript_aligns_whole_file(self):
        aligner = make_aligner()
        aligner._align_text = MagicMock(return_value=[{"start": 1.0, "end": 2.0}])
        emissions = torch.zeros(100, 4)

        result = aligner.align(
            "one two", "en", emissions, 20.0, "tokenizer",
            segments=[Segment(0, 1000, "one"), Segment(1000, 2000, "two")],
        )

        assert result == [{"start": 1.0, "end": 2.0}]
        aligner._align_text.assert_called_once_with(
            "one two", "en", emissions, 20.0, "tokenizer",
        )

    def test_long_transcript_aligns_in_chunks(self):
        """Long transcripts are aligned per window and shifted back in time."""
        aligner = make_aligner()
        word_times = {"first": (0.5, 1.0), "second": (5.2, 5.8)}
        aligner._align_text = MagicMock(
            side_effect=lambda text, *args: [
                {"text": text, "start": word_times[text][0], "end": word_times[text][1]}
            ]
        )
        stride = 20.0  # ms per emission frame
        ten_minutes_ms = 10 * 60 * 1000
        chunks_started = []
        aligner._on_chunk_started = lambda index, count: chunks_started.append((index, count))

        result = aligner.align(
            "first second", "en", ten_minutes_of_emissions(), stride, "tokenizer",
            segments=[
                Segment(0, 1000, "first"),
                Segment(ten_minutes_ms - 1000, ten_minutes_ms, "second"),
            ],
        )

        assert [call.args[0] for call in aligner._align_text.call_args_list] == ["first", "second"]
        assert chunks_started == [(1, 2), (2, 2)]
        # The first window starts at the beginning of the audio. The second one
        # reaches back over the unclaimed audio before its segment, as far as
        # allowed, plus ALIGNMENT_CHUNK_PADDING_MS
        reach_ms = ALIGNMENT_CHUNK_MAX_REACH_BACK_MS + ALIGNMENT_CHUNK_PADDING_MS
        second_offset = (ten_minutes_ms - 1000 - reach_ms) / 1000
        assert result == [
            {"text": "first", "start": 0.5, "end": 1.0},
            {"text": "second", "start": second_offset + 5.2, "end": second_offset + 5.8},
        ]
        # The second window gets just its own slice of the emissions
        second_emissions = aligner._align_text.call_args_list[1].args[2]
        assert second_emissions.size(0) == int((1000 + reach_ms) / stride)

    @pytest.mark.parametrize(
        "segments",
        [
            [Segment(0, 1000, "first"), Segment(0, 0, " ")],
            [Segment(0, 1000, "first"), Segment(599000, 599000, "second")],
        ],
        ids=["untimed_segment_without_text", "zero_length_segment"],
    )
    def test_segments_that_still_align_in_chunks(self, segments):
        aligner = make_aligner()
        aligner._align_text = MagicMock(
            side_effect=lambda text, *args: [{"text": text, "start": 0.5, "end": 0.5}]
        )

        aligner.align(
            " ".join(s.text for s in segments).strip(), "en",
            ten_minutes_of_emissions(), 20.0, "tokenizer", segments=segments,
        )

        texts = [call.args[0] for call in aligner._align_text.call_args_list]
        assert texts == [s.text for s in segments if s.text.strip()]

    def test_leading_zero_length_words_still_align_in_chunks(self):
        """Word-level timings can start with (0, 0) words; those times are not missing."""
        aligner = make_aligner()
        aligner._align_text = MagicMock(
            side_effect=lambda text, *args: [
                {"text": word, "start": 0.5, "end": 0.5} for word in text.split()
            ]
        )
        segments = [
            Segment(0, 0, "first"),
            Segment(0, 0, "second"),
            Segment(0, 1000, "third"),
            Segment(599000, 600000, "fourth"),
        ]

        aligner.align(
            "first second third fourth", "en", ten_minutes_of_emissions(), 20.0, "tokenizer",
            segments=segments,
        )

        texts = [call.args[0] for call in aligner._align_text.call_args_list]
        assert texts == ["first second third", "fourth"]

    def test_retries_chunk_whose_text_does_not_fit_with_wider_window(self):
        aligner = make_aligner()
        window_sizes = []

        def align_text(text, language, emissions, stride, tokenizer):
            window_sizes.append(emissions.size(0))
            if text == "second" and len(window_sizes) == 2:
                raise RuntimeError("targets length is too long for CTC.")
            return [{"text": text, "start": 0.0, "end": 0.1}]

        aligner._align_text = align_text
        ten_minutes_ms = 10 * 60 * 1000

        result = aligner.align(
            "first second", "en", ten_minutes_of_emissions(), 20.0, "tokenizer",
            segments=[
                Segment(0, 1000, "first"),
                Segment(ten_minutes_ms - 1000, ten_minutes_ms, "second"),
            ],
        )

        assert [word["text"] for word in result] == ["first", "second"]
        assert len(window_sizes) == 3
        assert window_sizes[2] > window_sizes[1]

    def test_chunk_with_a_few_bad_words_is_not_retried(self):
        """The wider window lets a chunk's last words drift into the next chunk."""
        aligner = make_aligner()
        aligner._align_text = MagicMock(return_value=[
            {"text": word, "start": start, "end": start + 0.5, "score": score}
            for word, start, score in [("x", 1.0, -0.1), ("y", 2.0, -0.1), ("z", 3.0, -9.0)]
        ])

        result = aligner._align_chunk_with_retry(
            "x y z", 10000, 20000, "en", ten_minutes_of_emissions(), 20.0, "tokenizer",
        )

        assert [word["text"] for word in result] == ["x", "y", "z"]
        aligner._align_text.assert_called_once()

    def test_spreads_words_of_a_chunk_that_fails_in_a_good_transcript(self):
        """One failed window does not fail the job, and gets evenly spread words."""
        aligner = make_aligner(
            preprocess_text=MagicMock(return_value=(None, ["<star>", "two", "words", "<star>"])),
        )
        good_words = "a b c d"

        def align_text(text, *args):
            if text == "two words":
                raise RuntimeError("targets length is too long for CTC.")
            return [
                {"text": word, "start": 0.1 * i, "end": 0.1 * i + 0.1}
                for i, word in enumerate(text.split())
            ]

        aligner._align_text = align_text

        result = aligner.align(
            f"{good_words} two words", "en", ten_minutes_of_emissions(), 20.0, "tokenizer",
            segments=[Segment(0, 1000, good_words), Segment(598000, 600000, "two words")],
        )

        assert [(w["text"], w["start"], w["end"]) for w in result[4:]] == [
            ("two", 598.0, 599.0),
            ("words", 599.0, 600.0),
        ]
        assert [word["text"] for word in result[:4]] == good_words.split()

    def test_chunk_without_evidence_for_most_words_is_spread_after_a_retry(self):
        aligner = make_aligner(
            preprocess_text=MagicMock(return_value=(None, ["<star>", "x", "<star>", "y", "<star>", "z"])),
        )
        aligner._align_text = MagicMock(return_value=[
            {"text": word, "start": 1.0, "end": 1.5, "score": score}
            for word, score in [("x", -9.0), ("y", -9.0), ("z", -0.1)]
        ])

        result = aligner._align_chunk_with_retry(
            "x y z", 598000, 600000, "en", ten_minutes_of_emissions(), 20.0, "tokenizer",
        )

        assert aligner._align_text.call_count == 2
        assert [word["start"] for word in result] == pytest.approx(
            [598.0, 598.0 + 2 / 3, 598.0 + 4 / 3]
        )

    def test_fails_when_most_of_the_transcript_has_no_evidence(self):
        aligner = make_aligner(
            preprocess_text=MagicMock(return_value=(None, ["<star>", "first", "<star>"])),
        )
        aligner._align_text = MagicMock(
            side_effect=RuntimeError("targets length is too long for CTC.")
        )

        with pytest.raises(AlignmentFailedError, match="does not match the audio"):
            aligner.align(
                "first", "en", ten_minutes_of_emissions(), 20.0, "tokenizer",
                segments=[Segment(100000, 100000, "first")],
            )

    def test_next_acoustic_start_shortens_padded_end_across_a_chunk_edge(self):
        from whisper_diarization.helpers import get_words_speaker_mapping

        aligner = make_aligner()
        aligner._align_text = MagicMock(
            side_effect=[
                [{"text": "first", "start": 298.0, "end": 305.0}],
                [{"text": "second", "start": 4.0, "end": 310.0}],
            ]
        )
        emissions = torch.zeros(int(20 * 60 * 1000 / 20.0), 4)

        result = aligner.align(
            "first second", "en", emissions, 20.0, "tokenizer",
            segments=[Segment(0, 300000, "first"), Segment(300000, 600000, "second")],
        )

        assert [(w["start"], w["end"]) for w in result] == [(298.0, 299.0), (299.0, 605.0)]
        mapped = get_words_speaker_mapping(result, [(0, 299500, 0), (299500, 1200000, 1)])
        assert [word["speaker"] for word in mapped] == [0, 0]

    def test_overlap_realignment_replaces_spread_words(self):
        """Evenly spread words have no evidence to protect from a joint alignment."""
        aligner = make_aligner(
            preprocess_text=MagicMock(
                return_value=(None, ["<star>", "two", "<star>", "words", "<star>"])
            ),
        )
        aligner._align_text = MagicMock(side_effect=RuntimeError("does not fit"))
        emissions = torch.zeros(1000, 4)

        aligned = aligner._align_chunk_with_retry(
            "two words", 4000, 8000, "en", emissions, 20.0, "tokenizer",
        )
        words = [{"text": "next", "start": 3.0, "end": 9.0, "score": -1.0}]
        aligner._align_text = MagicMock(return_value=[
            {"text": "two", "start": 0.0, "end": 0.1, "score": -9.0},
            {"text": "words", "start": 0.1, "end": 0.2, "score": -1.0},
            {"text": "next", "start": 0.2, "end": 0.3, "score": -1.0},
        ])

        aligner._realign_chunk_overlap(aligned, words, "en", emissions, 20.0, "tokenizer")

        assert aligned == []
        assert [word["text"] for word in words] == ["two", "words", "next"]

    def test_chunk_past_the_end_of_audio_uses_its_tail(self):
        aligner = make_aligner()
        aligner._align_text = MagicMock(return_value=[{"start": 0.0, "end": 1.0}])
        emissions = torch.zeros(500, 4)  # 10 s of audio

        result = aligner._align_chunk(
            "ghost", 60000, 62000, ALIGNMENT_CHUNK_PADDING_MS,
            "en", emissions, 20.0, "tokenizer",
        )

        assert aligner._align_text.call_args.args[2].size(0) == 100
        assert result == [{"start": 8.0, "end": 9.0}]

    def test_stops_when_cancelled(self):
        cancelled = []
        aligner = make_aligner(is_cancelled=lambda: bool(cancelled))

        def align_text(text, *args):
            cancelled.append(True)
            return [{"text": text, "start": 0.5, "end": 1.0}]

        aligner._align_text = MagicMock(side_effect=align_text)

        result = aligner.align(
            "first second", "en", ten_minutes_of_emissions(), 20.0, "tokenizer",
            segments=[Segment(0, 1000, "first"), Segment(599000, 600000, "second")],
        )

        assert result is None
        aligner._align_text.assert_called_once()

    def test_refuses_an_alignment_over_the_memory_budget(self, monkeypatch):
        monkeypatch.setattr(speaker_identifier, "ALIGNMENT_MAX_CTC_CELLS", 1000)
        get_alignments = MagicMock()
        aligner = make_aligner(
            preprocess_text=MagicMock(return_value=(["<star>", "a b", "<star>"], [])),
            get_alignments=get_alignments,
        )

        with pytest.raises(AlignmentFailedError, match="too long to align at once"):
            aligner.align("a", "en", ten_minutes_of_emissions(), 20.0, "tokenizer")

        get_alignments.assert_not_called()


@pytest.mark.skipif(
    (platform.system() == "Darwin" and platform.machine() == "x86_64")
    or platform.system() == "Windows",
    reason="Speaker identification dependencies crash on Windows and are unsupported on Intel Mac",
)
class TestTranscriptAlignerWithRealCtc:
    """Real local CTC, tiny vocabulary and seeded speech; no model downloads."""

    @pytest.fixture()
    def synthetic(self):
        from ctc_forced_aligner.ctc_forced_aligner import (
            get_alignments, get_spans, postprocess_results, preprocess_text,
        )

        aligner = make_aligner(
            preprocess_text=MagicMock(wraps=preprocess_text),
            get_alignments=MagicMock(wraps=get_alignments),
            get_spans=get_spans,
            postprocess_results=postprocess_results,
        )
        tokenizer = MagicMock(vocab_size=3, pad_token_id=0)
        tokenizer.get_vocab.return_value = {"<blank>": 0, "a": 1, "b": 2}
        logits = torch.randn(6000, 3, generator=torch.Generator().manual_seed(7)) * 0.01
        logits[:, 0] += 12
        logits[1000:1003, 1] += 24
        logits[2000:2003, 2] += 24
        emissions = torch.cat([logits.log_softmax(-1), torch.zeros(6000, 1)], dim=1)
        return aligner, emissions, tokenizer

    @pytest.mark.parametrize("timing", ["missing", "none", "mixed", "inverted"])
    def test_transcript_without_usable_times_aligns_in_one_pass(self, synthetic, timing):
        aligner, emissions, tokenizer = synthetic
        segments = {
            "missing": [Segment(0, 0, "a"), Segment(0, 0, "b")],
            "none": None,
            "mixed": [Segment(0, 1000, "a"), Segment(0, 0, "b")],
            "inverted": [Segment(0, 1000, "a"), Segment(3000, 2000, "b")],
        }[timing]

        result = aligner.align("a b", "en", emissions, 100.0, tokenizer, segments=segments)

        assert [word["text"] for word in result] == ["a", "b"]
        assert [word["start"] for word in result] == pytest.approx([100, 200], abs=0.3)
        assert aligner._get_alignments.call_count == 1

    def test_one_long_segment_does_not_affect_the_rest_of_the_file(self, synthetic):
        aligner, emissions, tokenizer = synthetic

        result = aligner.align(
            "a b", "en", emissions, 100.0, tokenizer,
            segments=[Segment(1000, 150000, "a"), Segment(150000, 590000, "b")],
        )

        assert [word["start"] for word in result] == pytest.approx([100, 200], abs=0.3)
        assert aligner._get_alignments.call_count == 2

    def test_retries_chunk_whose_timestamps_drifted(self, synthetic):
        """A window that misses its speech aligns without error but is retried."""
        aligner, emissions, tokenizer = synthetic
        # "b" is spoken at 490 s, after the end its segment claims
        emissions[4900:4903] = emissions[2000:2003].clone()
        emissions[2000:2003] = emissions[:3]

        result = aligner.align(
            "a b", "en", emissions, 100.0, tokenizer,
            segments=[Segment(95000, 105000, "a"), Segment(440000, 445000, "b")],
        )

        assert [word["start"] for word in result] == pytest.approx([100, 490], abs=0.3)
        assert aligner._get_alignments.call_count == 3

    def test_window_reaches_back_over_audio_no_segment_claims(self, synthetic):
        """Whisper can stamp a run of segments with one time after their speech."""
        aligner, emissions, tokenizer = synthetic
        # "b" is spoken at 300 s, but its segment claims 440 s, too late for
        # even the retry's padding to reach
        emissions[3000:3003] = emissions[2000:2003].clone()
        emissions[2000:2003] = emissions[:3]

        result = aligner.align(
            "a b", "en", emissions, 100.0, tokenizer,
            segments=[Segment(95000, 105000, "a"), Segment(440000, 440000, "b")],
        )

        assert [word["start"] for word in result] == pytest.approx([100, 300], abs=0.3)
        # Found on the first try, with no retry
        assert aligner._get_alignments.call_count == 2

    def test_identical_timestamps_are_an_error_not_a_single_time(self, synthetic):
        aligner, emissions, tokenizer = synthetic
        text = " ".join(["a b"] * 400)

        with pytest.raises(AlignmentFailedError, match="does not match the audio"):
            aligner.align(
                text, "en", emissions, 100.0, tokenizer,
                segments=[Segment(100000, 100000, text)],
            )

    def test_text_without_speech_in_the_audio_is_an_error(self, synthetic):
        aligner, emissions, tokenizer = synthetic
        # Excellent blank/star scores cannot compensate for absent speech
        emissions[:, :3] = -12
        emissions[:, 0] = 0

        with pytest.raises(AlignmentFailedError, match="does not match the audio"):
            aligner.align(
                "a b", "en", emissions, 100.0, tokenizer,
                segments=[Segment(95000, 105000, "a"), Segment(195000, 205000, "b")],
            )

    def test_letterless_words_are_not_retried(self, synthetic):
        """Digits and punctuation have no letters to match, so are not unconfident."""
        aligner, emissions, tokenizer = synthetic

        result = aligner._align_chunk_with_retry(
            "a 5 ??? b", 0, 300000, "en", emissions, 100.0, tokenizer,
        )

        assert [word["text"] for word in result] == ["a", "5", "???", "b"]
        assert [word["score"] for word in result[1:3]] == [0.0, 0.0]
        aligner._get_alignments.assert_called_once()

    def test_digits_past_the_end_of_audio_do_not_crash(self, synthetic):
        """The window clamps to a single frame, too short to align, so it is spread."""
        aligner, emissions, tokenizer = synthetic

        result = aligner.align(
            "a b 2024", "en", emissions, 100.0, tokenizer,
            segments=[
                Segment(95000, 105000, "a"),
                Segment(195000, 205000, "b"),
                Segment(1000000, 1000000, "2024"),
            ],
        )

        assert [word["text"] for word in result] == ["a", "b", "2024"]
        assert result[2]["start"] == pytest.approx(600)
        # Only the first window reaches the aligner
        aligner._get_alignments.assert_called_once()

    @pytest.mark.parametrize(
        "targets, expected_path",
        [
            ([3], [3]),
            ([1, 2, 1, 2, 1], [1, 2, 1, 2, 1]),
            ([1, 1, 2, 1], [1, 0, 1, 2, 1]),
        ],
        ids=["single_frame", "exact_fit", "exact_fit_with_repeat"],
    )
    def test_aligner_handles_frames_that_exactly_fit_the_targets(self, targets, expected_path):
        """These segfaulted, which would end this whole test session if they regress."""
        import numpy as np
        from ctc_forced_aligner.ctc_forced_aligner.alignment_utils import forced_align

        path, _scores = forced_align(
            np.full((1, len(expected_path), 4), -1.4, dtype=np.float32),
            np.asarray([targets], dtype=np.int64),
        )

        assert path[0].tolist() == expected_path

    def test_aligner_still_rejects_too_few_frames(self):
        import numpy as np
        from ctc_forced_aligner.ctc_forced_aligner.alignment_utils import forced_align

        with pytest.raises(RuntimeError, match="too long for CTC"):
            forced_align(
                np.full((1, 4, 4), -1.4, dtype=np.float32),
                np.asarray([[1, 1, 2, 1]], dtype=np.int64),
            )

    @pytest.mark.parametrize("frames, targets", [(2, [3]), (6, [1, 2, 1, 2, 1]), (6, [1, 1, 2, 1])])
    def test_aligner_accepts_one_spare_frame(self, frames, targets):
        import numpy as np
        from ctc_forced_aligner.ctc_forced_aligner.alignment_utils import forced_align

        path, _scores = forced_align(
            np.full((1, frames, 4), -1.4, dtype=np.float32),
            np.asarray([targets], dtype=np.int64),
        )

        assert path.shape == (1, frames)

    def test_boundary_speaker_is_preserved(self, synthetic):
        from whisper_diarization.helpers import get_words_speaker_mapping

        aligner, emissions, tokenizer = synthetic
        emissions[2980:2983] = emissions[1000:1003].clone()
        emissions[2990:2993] = emissions[2000:2003].clone()
        # The ordinary path has no trailing star. Keep the following word's
        # blank cost modest so it can retain the first word before that speech.
        emissions[2990:2993, 0] = -0.7
        emissions[2990:2993, 2] = -0.7
        emissions[1000:1003] = emissions[:3]
        emissions[2000:2003] = emissions[:3]

        result = aligner.align(
            "a b", "en", emissions, 100.0, tokenizer,
            segments=[Segment(0, 300000, "a"), Segment(300000, 600000, "b")],
        )

        assert [word["start"] for word in result] == pytest.approx([298, 299], abs=0.3)
        assert result[0]["end"] == result[1]["start"]
        mapping = get_words_speaker_mapping(result, [(0, 299500, 0), (299500, 600000, 1)])
        assert [word["speaker"] for word in mapping] == [0, 0]

    def test_realigns_words_swapped_across_chunk_edge(self, synthetic):
        """Repeats that neighbouring windows took from each other are re-aligned jointly."""
        from whisper_diarization.helpers import get_words_speaker_mapping

        aligner, emissions, tokenizer = synthetic
        emissions[2980:2983] = emissions[1000:1003].clone()
        emissions[3020:3023] = emissions[1000:1003].clone()
        emissions[1000:1003] = emissions[:3]
        real_align_text = aligner._align_text
        # Each window took the other's "a": 302 s for the first, 298 s for
        # the second (its window starts 5 s before 300 s)
        swapped = iter([
            [{"text": "a", "start": 302.0, "end": 302.3, "score": -0.1}],
            [{"text": "a", "start": 3.0, "end": 3.3, "score": -0.1}],
        ])
        aligner._align_text = MagicMock(
            side_effect=lambda text, *args: next(swapped, None) or real_align_text(text, *args)
        )

        result = aligner.align(
            "a a", "en", emissions, 100.0, tokenizer,
            segments=[Segment(0, 300000, "a"), Segment(300000, 600000, "a")],
        )

        assert aligner._align_text.call_args.args[0] == "a a"
        assert [word["start"] for word in result] == pytest.approx([298, 302], abs=0.3)
        mapping = get_words_speaker_mapping(result, [(0, 300000, 0), (300000, 600000, 1)])
        assert [word["speaker"] for word in mapping] == [0, 1]

    def test_realigned_word_can_move_back_towards_the_word_kept_before_it(self, synthetic):
        """A word that drifted past the next window's first word can return before it."""
        aligner, emissions, tokenizer = synthetic
        a_row, b_row = emissions[1000].clone(), emissions[2000].clone()
        emissions[1000:1003] = emissions[2000:2003] = emissions[:3]
        # One frame per letter, so the star before the second window's "a"
        # cannot take speech frames before the start it reports
        for frame, row in [(2900, b_row), (2970, a_row), (3010, b_row), (3030, a_row)]:
            emissions[frame] = row
        real_align_text = aligner._align_text
        # The first window took the second window's "a" at 303 s, past its "b"
        first_window = iter([[
            {"text": "b", "start": 290.0, "end": 291.0, "score": -0.1},
            {"text": "a", "start": 303.0, "end": 303.3, "score": -0.1},
        ]])
        aligner._align_text = MagicMock(
            side_effect=lambda text, *args: next(first_window, None) or real_align_text(text, *args)
        )

        result = aligner.align(
            "b a b a", "en", emissions, 100.0, tokenizer,
            segments=[Segment(0, 300000, "b a"), Segment(300000, 600000, "b a")],
        )

        assert [word["text"] for word in result] == ["b", "a", "b", "a"]
        assert [word["start"] for word in result] == pytest.approx([290, 297, 301, 303], abs=0.3)

    @pytest.mark.parametrize("text, joins", [("ab", True), ("a b", False)])
    def test_japanese_is_aligned_character_by_character(self, synthetic, text, joins):
        aligner, emissions, tokenizer = synthetic

        result = aligner.align(text, "ja", emissions, 100.0, tokenizer)

        # Spaces are not aligned as characters; they only end a word
        assert [word["text"] for word in result] == ["a", "b"]
        assert [word["start"] for word in result] == pytest.approx([100, 200], abs=0.3)
        assert "joins_previous" not in result[0]
        assert result[1].get("joins_previous", False) is joins

    def test_preprocess_keeps_japanese_spacing(self):
        from ctc_forced_aligner.ctc_forced_aligner import preprocess_text

        aligner = make_aligner(preprocess_text=preprocess_text)

        _tokens, text_starred, joins = aligner._preprocess_for_alignment("日本 語", "ja")

        assert [text for text in text_starred if text != "<star>"] == ["日", "本", "語"]
        assert joins == [False, True, False]

    def test_long_unspaced_word_is_aligned_in_pieces(self, synthetic):
        aligner, emissions, tokenizer = synthetic
        a_row, b_row = emissions[1000].clone(), emissions[2000].clone()
        emissions[1000:1003] = emissions[2000:2003] = emissions[:3]
        # Alternating "a"/"b" speech, one letter every 0.4 s from 100 s
        for k in range(26):
            emissions[1000 + 4 * k] = a_row if k % 2 == 0 else b_row

        result = aligner.align("ab" * 13, "en", emissions, 100.0, tokenizer)

        assert [word["text"] for word in result] == ["ababababababa", "babababababab"]
        assert [word["start"] for word in result] == pytest.approx([100, 105.2], abs=0.3)
        assert "joins_previous" not in result[0]
        assert result[1]["joins_previous"] is True
