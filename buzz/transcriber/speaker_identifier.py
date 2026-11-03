"""Run speaker identification outside the transcription viewer.

Folder watch transcriptions are exported without any user interaction, so the
diarization has to run headless, straight on the segments returned by the
transcriber and before the output files are written.
"""

import logging
import math
import re
import unicodedata
from typing import Callable, Dict, List, Optional

from buzz.locale import _
from buzz.transcriber.transcriber import Segment

# CTC forced alignment keeps back-pointers for every (frame, token) pair it
# explores, so its memory grows with audio length times transcript length:
# a two hour talk needs ~13 GB and gets the app killed by the OOM killer.
# Longer transcripts are therefore aligned in windows of consecutive segments.
ALIGNMENT_CHUNK_DURATION_MS = 5 * 60 * 1000
# Audio added around each window, as segment timestamps are not exact
ALIGNMENT_CHUNK_PADDING_MS = 5 * 1000
# How far a window reaches back over audio that no segment claims. Whisper can
# lose track and stamp a run of segments with one later time, so their speech
# lies in the gap before them. The limit bounds a window after a long silence.
ALIGNMENT_CHUNK_MAX_REACH_BACK_MS = ALIGNMENT_CHUNK_DURATION_MS
# Wider padding for a window that did not match its audio. Only for windows where
# most words failed: stars let the last words of any other window drift forward
# into the extra audio, up to this far.
ALIGNMENT_CHUNK_RETRY_PADDING_MS = 60 * 1000
# Largest alignment allowed, at two bits per frame/state cell: about 2 GB. A
# window never gets close; this bounds segments claiming most of a long file and
# transcripts aligned in one pass, which reach it at about 45 minutes of speech.
ALIGNMENT_MAX_CTC_CELLS = 8_000_000_000
# Blank/star probabilities can hide a bad match, so only letters count as
# evidence. Words below this mean log probability (about 0.007) did not match.
ALIGNMENT_MIN_TOKEN_LOG_PROB = -5.0
# Thai, Lao, Khmer and Burmese put no spaces between words, so a "word" can be
# a whole phrase: one timestamp then hides speaker changes inside it, and on
# long files it may not fit the CTC budget. Longer words are aligned in pieces.
ALIGNMENT_MAX_WORD_CHARS = 24
# Thai and Lao vowels written before the consonant they follow. uroman moves them
# after it ("เป็น" is "pen"), so splitting after one reorders the letters.
LEADING_VOWELS = frozenset("เแโใไເແໂໃໄ")
# Raised by the aligner, usually when text does not fit into its audio
ALIGNMENT_ERRORS = (RuntimeError, ValueError, AssertionError)


class AlignmentFailedError(RuntimeError):
    """The transcript cannot be aligned to the audio; the message is for the user."""


def build_speaker_segments(
    identification_result: List[Dict],
    speaker_mapping: Optional[Dict[str, str]] = None,
    merge_speaker_sentences: bool = True,
) -> List[Segment]:
    """Turn the diarization result into segments carrying speaker labels."""
    speaker_mapping = speaker_mapping or {}

    segments: List[Segment] = []
    previous_segment = None

    for entry in identification_result:
        speaker_name = speaker_mapping.get(entry["speaker"], entry["speaker"])

        if merge_speaker_sentences:
            if previous_segment and previous_segment["speaker"] == speaker_name:
                previous_segment["end_time"] = entry["end_time"]
                previous_segment["text"] += " " + entry["text"]
                continue

            if previous_segment:
                segments.append(
                    Segment(
                        start=previous_segment["start_time"],
                        end=previous_segment["end_time"],
                        text=previous_segment["text"],
                        speaker=previous_segment["speaker"],
                    )
                )

            previous_segment = {
                "start_time": entry["start_time"],
                "end_time": entry["end_time"],
                "speaker": speaker_name,
                "text": entry["text"],
            }
        else:
            segments.append(
                Segment(
                    start=entry["start_time"],
                    end=entry["end_time"],
                    text=entry["text"],
                    speaker=speaker_name,
                )
            )

    if previous_segment:
        segments.append(
            Segment(
                start=previous_segment["start_time"],
                end=previous_segment["end_time"],
                text=previous_segment["text"],
                speaker=previous_segment["speaker"],
            )
        )

    return segments


def identify_speakers(
    file_path: str,
    segments: List[Segment],
    language: Optional[str] = None,
    diarizer: str = "msdd",
    num_speakers: Optional[int] = None,
    merge_speaker_sentences: bool = True,
) -> List[Segment]:
    """Label ``segments`` with automatic speaker names.

    Runs synchronously on the calling thread. Returns the original segments
    unchanged if the identification fails, so a transcription is still
    exported when speakers cannot be identified.
    """
    if not segments:
        return segments

    # Imported here to keep the heavy diarization dependencies out of the
    # startup path of apps that never identify speakers.
    from buzz.widgets.transcription_viewer.speaker_identification_widget import (
        IdentificationWorker,
    )

    worker = IdentificationWorker(
        transcription=None,
        transcription_service=None,
        diarizer=diarizer,
        num_speakers=num_speakers if diarizer == "msdd" else None,
        segments=segments,
        file_path=file_path,
        language=language,
    )

    result: List[Dict] = []
    errors: List[str] = []

    worker.finished.connect(result.extend)
    worker.error.connect(errors.append)
    worker.progress_update.connect(
        lambda progress: logging.debug("Speaker identification: %s", progress)
    )

    try:
        worker.run()
    except Exception:
        logging.exception("Speaker identification failed")
        return segments

    if errors:
        logging.warning("Speaker identification failed: %s", errors[0])
        return segments

    if not result:
        logging.warning("Speaker identification returned no speakers")
        return segments

    return build_speaker_segments(
        result, merge_speaker_sentences=merge_speaker_sentences
    )


def join_segment_texts(texts):
    """Join segment texts into one transcript for alignment."""
    return re.sub(r" {2,}", " ", " ".join(texts))


def mark_join(word, joins_previous):
    """Flag a piece that continues the previous word; plain words lack the key."""
    if joins_previous:
        word["joins_previous"] = True
    return word


def segment_times_ms(segment):
    """Start and end of a stored ``TranscriptionSegment`` or a ``Segment``."""
    if hasattr(segment, "start_time"):
        return segment.start_time, segment.end_time
    return segment.start, segment.end


def have_usable_times(segments):
    """Whether the times of ``segments``, in spoken order, can place them in windows.

    Zero-length segments at real positions (common with word-level timings)
    still chunk fine, including words at (0, 0) before the first timed one.
    Missing or inverted times do not, nor a (0, 0) segment after timed ones.
    """
    timed = False
    for segment in segments:
        start, end = segment_times_ms(segment)
        if start is None or end is None or start > end:
            return False
        if end > 0:
            timed = True
        elif timed:
            return False
    return timed


def build_alignment_chunks(segments, chunk_duration_ms=ALIGNMENT_CHUNK_DURATION_MS):
    """Group consecutive segments into windows of about ``chunk_duration_ms``.

    A longer segment gets a window of its own. Returns ``(text, start_ms,
    end_ms)`` tuples, skipping windows without text.
    """
    # Sort by start alone: the stable sort keeps the spoken order of segments
    # that start together, whatever their ends
    segments = sorted(segments, key=lambda segment: segment_times_ms(segment)[0])
    chunks = []
    texts = []
    chunk_start = chunk_end = 0

    def flush():
        text = join_segment_texts(texts).strip()
        if text:
            chunks.append((text, chunk_start, chunk_end))

    for segment in segments:
        start, end = segment_times_ms(segment)
        if texts and end - chunk_start > chunk_duration_ms:
            flush()
            texts = []
        if not texts:
            chunk_start = chunk_end = start
        texts.append(segment.text)
        chunk_end = max(chunk_end, end)
    if texts:
        flush()

    return chunks


def clamp_chunk_words(words, audio_end, previous_word=None):
    """Reconcile overlaps without replacing acoustic starts with segment times.

    Keep starts ordered and inside the audio. A previous word's padded end
    must yield to the next acoustic start, including across chunk boundaries.
    """
    for word in words:
        previous_start = previous_word["start"] if previous_word is not None else 0.0
        word["start"] = min(max(word["start"], previous_start), audio_end)
        word["end"] = min(max(word["end"], word["start"]), audio_end)
        if previous_word is not None:
            previous_word["end"] = min(previous_word["end"], word["start"])
        previous_word = word


def can_split_before(word, index):
    """Whether a piece of ``word`` may start at ``index``.

    Not on a combining mark, so vowel and tone marks stay with their consonant,
    and not after a vowel written before its consonant.
    """
    return (
        not unicodedata.category(word[index]).startswith("M")
        and word[index - 1] not in LEADING_VOWELS
    )


def split_long_words(text, max_chars=ALIGNMENT_MAX_WORD_CHARS):
    """Split words longer than ``max_chars`` into about equal pieces.

    Returns the pieces and, for each, whether it continues the previous word.
    Pieces split only where ``can_split_before`` allows. They keep within
    ``max_chars`` where that allows, so splitting them again keeps them whole,
    as re-aligning contested words does.
    """
    pieces = []
    joins = []
    for word in text.split():
        start = 0
        while start < len(word):
            remaining = len(word) - start
            end = start + math.ceil(remaining / math.ceil(remaining / max_chars))
            split = end
            while start + 1 < split < len(word) and not can_split_before(word, split):
                split -= 1
            if split < len(word) and not can_split_before(word, split):
                # The whole piece is one cluster of marks: end after it instead
                split = end
                while split < len(word) and not can_split_before(word, split):
                    split += 1
            pieces.append(word[start:split])
            joins.append(start > 0)
            start = split
    return pieces, joins


def merge_word_pieces(word_speaker_mapping, word_timestamps):
    """Rejoin pieces of a split word that were assigned the same speaker.

    The sentence mapping puts a space after every entry; a word whose pieces
    went to different speakers stays split at the speaker change.
    """
    merged = []
    for entry, word in zip(word_speaker_mapping, word_timestamps):
        if (
            word.get("joins_previous")
            and merged
            and merged[-1]["speaker"] == entry["speaker"]
        ):
            merged[-1]["word"] += entry["word"]
            merged[-1]["end_time"] = entry["end_time"]
        else:
            merged.append(entry)
    return merged


def lexical_runs(tokens, spans, blank):
    """Letter runs of each non-star token, without blank/star padding."""
    return [
        [run for run in span if run.label not in (blank, "<star>")]
        for token, span in zip(tokens, spans) if token != "<star>"
    ]


def mean_run_score(runs, scores):
    """Mean letter log probability of runs.

    Digits and punctuation romanize to no letters, so have no runs. They are
    not evidence of a bad match, which would send nearly every window of real
    speech to a wider retry, so they score 0. ``get_alignments`` returns
    inclusive run ends.
    """
    if not runs:
        return 0.0
    run_scores = [float(scores[run.start:run.end + 1].mean()) for run in runs]
    return sum(run_scores) / len(run_scores)


def count_unconfident_words(words):
    """Words whose letters matched the audio worse than the confidence floor."""
    return sum(
        1 for word in words
        if not word.get("score", 0.0) >= ALIGNMENT_MIN_TOKEN_LOG_PROB
    )


def most_words_unconfident(words):
    return 2 * count_unconfident_words(words) >= len(words)


class TranscriptAligner:
    """Finds when each word of a transcript is spoken, within bounded memory.

    Takes the ``ctc_forced_aligner`` functions as arguments, as that package is
    slow to import and is only imported once speaker identification starts.
    """

    def __init__(
        self,
        preprocess_text: Callable,
        get_alignments: Callable,
        get_spans: Callable,
        postprocess_results: Callable,
        langs_to_iso: Dict[str, str],
        is_cancelled: Callable[[], bool] = lambda: False,
        on_chunk_started: Callable[[int, int], None] = lambda _index, _count: None,
    ):
        self._preprocess_text = preprocess_text
        self._get_alignments = get_alignments
        self._get_spans = get_spans
        self._postprocess_results = postprocess_results
        self._langs_to_iso = langs_to_iso
        self._is_cancelled = is_cancelled
        self._on_chunk_started = on_chunk_started

    def align(self, full_transcript, language, emissions, stride, tokenizer, segments=None):
        """Word timestamps for the transcript, or None if cancelled.

        Raises ``AlignmentFailedError`` when the transcript does not match the audio.
        """
        audio_duration_ms = emissions.size(0) * stride
        # An empty transcript of any length gets the aligner's error here,
        # before diarization runs only to produce an empty sentence
        if audio_duration_ms <= ALIGNMENT_CHUNK_DURATION_MS or not full_transcript.strip():
            return self._align_text(full_transcript, language, emissions, stride, tokenizer)

        emissions = emissions.cpu()
        # Segments without text are not aligned, so their times do not matter
        segments = [segment for segment in segments or [] if segment.text.strip()]
        if have_usable_times(segments):
            words = self._align_chunks(segments, language, emissions, stride, tokenizer)
        else:
            words = self._align_text(full_transcript, language, emissions, stride, tokenizer)

        if words is not None and most_words_unconfident(words):
            raise AlignmentFailedError(_(
                "Most of the transcript does not match the audio. "
                "Check that the audio file, language and timestamps are correct."
            ))
        return words

    def _align_chunks(self, segments, language, emissions, stride, tokenizer):
        chunks = build_alignment_chunks(segments)
        logging.debug("Speaker identification: Aligning %d chunks of transcript", len(chunks))
        audio_end = emissions.size(0) * stride / 1000

        word_timestamps = []
        for index, (text, start_ms, end_ms) in enumerate(chunks):
            if self._is_cancelled():
                return None
            self._on_chunk_started(index + 1, len(chunks))
            # Reach back to where the previous window's speech ended, so no
            # audio between windows is left out
            previous_end_ms = 0
            if word_timestamps:
                previous_end_ms = min(chunks[index - 1][2], word_timestamps[-1]["end"] * 1000)
            earliest_ms = max(previous_end_ms, start_ms - ALIGNMENT_CHUNK_MAX_REACH_BACK_MS)
            words = self._align_chunk_with_retry(
                text, start_ms, end_ms, language, emissions, stride, tokenizer,
                earliest_ms=earliest_ms,
            )
            self._realign_chunk_overlap(
                word_timestamps, words, language, emissions, stride, tokenizer,
            )
            clamp_chunk_words(
                words, audio_end, word_timestamps[-1] if word_timestamps else None,
            )
            word_timestamps.extend(words)
        return word_timestamps

    def _realign_chunk_overlap(self, aligned, words, language, emissions, stride, tokenizer):
        """Jointly re-align words that neighbouring windows put out of order.

        Windows are aligned independently, so a window's last word can match
        a repeat in the next window's padding while the next window takes the
        earlier occurrence ("a" at 302 s and 298 s). Clamping alone would then
        move a correctly placed word onto the other's speech. Aligning the
        contested words together over the audio between the words kept on
        either side restores their spoken order. Updates ``aligned`` and
        ``words`` in place.
        """
        if not aligned or not words or aligned[-1]["start"] <= words[0]["start"]:
            return
        tail = len(aligned)
        while tail > 0 and aligned[tail - 1]["start"] > words[0]["start"]:
            tail -= 1
        head = 0
        while head < len(words) and words[head]["start"] < aligned[-1]["start"]:
            head += 1
        contested = aligned[tail:] + words[:head]

        # Words kept on either side bound the window, so order is preserved.
        # A word that drifted past the next window's first word may belong
        # before it, so the window reaches back to the word kept before.
        start = min(word["start"] for word in contested)
        if tail > 0:
            start = min(start, aligned[tail - 1]["end"])
        end = max(word["end"] for word in contested)
        if head < len(words):
            end = min(end, words[head]["start"])
        start_frame = max(0, math.floor(start * 1000 / stride))
        end_frame = min(emissions.size(0), math.ceil(end * 1000 / stride))
        if (
            end_frame <= start_frame
            or (end_frame - start_frame) * stride > ALIGNMENT_CHUNK_DURATION_MS
        ):
            return

        try:
            joint = self._align_frames(
                " ".join(word["text"] for word in contested), language,
                emissions, start_frame, end_frame, stride, tokenizer,
            )
        except ALIGNMENT_ERRORS as e:
            logging.warning(
                "Speaker identification: Failed to re-align %d overlapping words "
                "at %.1f-%.1f s: %s", len(contested), start, end, e,
            )
            return
        if (
            len(joint) != len(contested)
            or count_unconfident_words(joint) > count_unconfident_words(contested)
        ):
            return

        # The contested words are already short pieces of split words
        for word, previous in zip(joint, contested):
            mark_join(word, previous.get("joins_previous"))
        del aligned[tail:]
        words[:head] = joint

    def _align_chunk_with_retry(
        self, text, start_ms, end_ms, language, emissions, stride, tokenizer,
        earliest_ms=None,
    ):
        for padding_ms in (ALIGNMENT_CHUNK_PADDING_MS, ALIGNMENT_CHUNK_RETRY_PADDING_MS):
            try:
                words = self._align_chunk(
                    text, start_ms, end_ms, padding_ms, language, emissions, stride, tokenizer,
                    earliest_ms=earliest_ms,
                )
            except ALIGNMENT_ERRORS as e:
                # Usually the text did not fit into the audio of its window
                logging.warning(
                    "Speaker identification: Failed to align chunk %d-%d ms "
                    "with %d ms padding: %s", start_ms, end_ms, padding_ms, e,
                )
                continue
            # About 4% of real words are mumbled or hallucinated, which says
            # nothing about the window. CTC also returns a path when the speech
            # lies outside the window, and then most words have no evidence.
            if not most_words_unconfident(words):
                return words
            logging.warning(
                "Speaker identification: Most of %d words in chunk %d-%d ms "
                "lack acoustic evidence with %d ms padding",
                len(words), start_ms, end_ms, padding_ms,
            )

        # Spread the words evenly over the window rather than failing the whole
        # identification because of one window. These times have no acoustic
        # evidence, so overlap re-alignment may replace them, and ``align`` fails
        # when this is true of most of the transcript.
        _tokens, text_starred, joins = self._preprocess_for_alignment(text, language)
        words = [word for word in text_starred if word != "<star>"]
        duration = (end_ms - start_ms) / 1000 / max(len(words), 1)
        return [
            mark_join({
                "text": word,
                "start": start_ms / 1000 + i * duration,
                "end": start_ms / 1000 + (i + 1) * duration,
                "score": float("-inf"),
            }, joins_previous)
            for i, (word, joins_previous) in enumerate(zip(words, joins))
        ]

    def _align_chunk(
        self, text, start_ms, end_ms, padding_ms, language, emissions, stride, tokenizer,
        earliest_ms=None,
    ):
        """Align a window's text to its audio, padded on both sides.

        ``earliest_ms`` lets the window start before ``start_ms``, over audio
        no other window covers.
        """
        window_start_ms = start_ms if earliest_ms is None else min(start_ms, earliest_ms)
        start_frame = max(0, int((window_start_ms - padding_ms) / stride))
        end_frame = min(emissions.size(0), math.ceil((end_ms + padding_ms) / stride))
        # Text whose timestamps run past the end of the audio (Whisper
        # hallucinations, trimmed files) is aligned to the tail of the audio
        min_frames = max(1, math.ceil((end_ms - start_ms) / stride))
        start_frame = max(0, min(start_frame, end_frame - min_frames))
        return self._align_frames(
            text, language, emissions, start_frame, end_frame, stride, tokenizer,
        )

    def _align_frames(
        self, text, language, emissions, start_frame, end_frame, stride, tokenizer,
    ):
        """Align text to ``emissions[start_frame:end_frame]``, in audio time."""
        word_timestamps = self._align_text(
            text, language, emissions[start_frame:end_frame], stride, tokenizer,
        )
        offset = start_frame * stride / 1000
        for word in word_timestamps:
            word["start"] += offset
            word["end"] += offset
        return word_timestamps

    def _preprocess_for_alignment(self, text, language):
        """``preprocess_text`` with long unspaced words aligned in pieces.

        Also returns, for each non-star text, whether it continues the
        previous word without a space.
        """
        iso_language = self._langs_to_iso[language]
        if iso_language in ("jpn", "chi"):
            # preprocess_text aligns these character by character, spaces
            # included; drop the spaces and remember where they were
            pieces = text.split()
            joins = [index > 0 for piece in pieces for index in range(len(piece))]
            text = "".join(pieces)
        else:
            pieces, joins = split_long_words(text)
            text = " ".join(pieces)
        tokens_starred, text_starred = self._preprocess_text(
            text, romanize=True, language=iso_language,
        )
        texts = sum(1 for word in text_starred if word != "<star>")
        if len(joins) != texts:
            joins = [False] * texts
        return tokens_starred, text_starred, joins

    def _align_text(self, text, language, emissions, stride, tokenizer):
        frames = emissions.size(0)
        # get_alignments squeezes a one-frame path into a plain number and fails
        if frames < 2:
            raise RuntimeError("Cannot align text to a single frame of audio.")

        tokens_starred, text_starred, joins = self._preprocess_for_alignment(text, language)

        targets = len(" ".join(tokens_starred).split())
        if (2 * targets + 2) * max(frames - targets, 0) > ALIGNMENT_MAX_CTC_CELLS:
            raise AlignmentFailedError(_(
                "This transcript is too long to align at once. "
                "Its segments may have no usable timestamps."
            ))

        segments, scores, blank_token = self._get_alignments(emissions, tokens_starred, tokenizer)
        spans = self._get_spans(tokens_starred, segments, blank_token)

        word_timestamps = self._postprocess_results(text_starred, spans, stride, scores)
        # postprocess_results also averages the blank padding, which hides a
        # bad match; score the letters alone so windows can be validated
        flat_scores = scores.reshape(-1)
        for word, runs, joins_previous in zip(
            word_timestamps, lexical_runs(tokens_starred, spans, blank_token), joins,
        ):
            word["score"] = mean_run_score(runs, flat_scores)
            mark_join(word, joins_previous)
        return word_timestamps
