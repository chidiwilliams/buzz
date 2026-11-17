"""
Hallucination Flagger plugin for Buzz.

Whisper-family models occasionally "hallucinate" during silence, music or
noise -- inventing text that was never actually spoken. This matters most for
deaf/hard-of-hearing users of offline captions, who have no audio to check
the text against. This plugin runs a cheap, heuristic pass over the segments
right after transcription and flags (never deletes or edits) the ones that
look hallucinated, so they can be reviewed instead of trusted as real speech.

v1 implements the two cheapest, highest-confidence heuristics from the
original feature request (buzz#1570):

1. Exact match against a short list of well-known Whisper "silence junk"
   phrases, matched against the *whole* (normalized) segment, never as a
   substring -- so a real sentence that happens to mention "music" or
   "subscribe" is never flagged.
2. A word or short phrase (1-3 words) repeating 3+ times in a row within one
   segment -- the classic silence feedback-loop pattern (e.g. "the the the",
   or "I don't know I don't know I don't know").

VAD-gap and logprob-based checks from the issue are intentionally left out of
v1: Buzz already discards that data in whisper_file_transcriber.py, so wiring
it back in is separate follow-up work, not part of this plugin.

Flagged segments get a `{"suspect": "true", "suspect_reason": "..."}` entry
appended to their `metadata` list. The transcription viewer already renders
segment metadata as a tooltip, so no viewer changes are needed for v1.
"""

import logging
import re
from typing import List

from buzz.plugins.base import (
    BuzzPlugin,
    PluginContext,
    PluginMetadata,
    plugin_gettext,
)
from buzz.transcriber.transcriber import Segment

logger = logging.getLogger(__name__)

# Translator for this plugin's user-facing strings. See locale/ for
# translations; missing strings fall through to English unchanged.
_ = plugin_gettext(__file__)

# Known phrases Whisper tends to invent over silence, music or noise. Checked
# against the *entire* normalized segment text, never as a substring, so a
# real sentence that happens to contain similar words is left alone.
JUNK_PHRASES = {
    "thanks for watching",
    "thank you for watching",
    "thanks for listening",
    "thank you for listening",
    "please subscribe",
    "like and subscribe",
    "subscribe to my channel",
    "music",
    "applause",
}

# A word or short (<=3-word) phrase repeating 3+ times in a row, e.g.
# "the the the" or "thank you thank you thank you". Runs against the
# *normalized* text (see below), not the raw segment, so punctuation between
# repeats -- "Thank you. Thank you. Thank you." is one of the most common
# real Whisper silence loops -- doesn't hide the repetition. `[\w']+` (rather
# than bare `\w+`) keeps a contraction like "don't" as a single token instead
# of splitting on the apostrophe.
_REPEAT_LOOP_RE = re.compile(r"\b([\w']+(?:\s+[\w']+){0,2})\b(?:\s+\1\b){2,}")

# Strip everything but letters, digits, spaces and apostrophes (so
# contractions survive as one token) so punctuation variants of the same
# junk phrase -- "Thanks for watching!", "[Music]", "(music)" -- and
# punctuation *between* repeats both normalize down to the same bare,
# whitespace-separated words.
_NORMALIZE_RE = re.compile(r"[^\w\s']")


def _normalize(text: str) -> str:
    return _NORMALIZE_RE.sub(" ", text).strip().lower()


def check(text: str) -> str:
    """Return a short reason string if `text` looks hallucinated, else "".

    Pure string matching -- no model inference, no I/O -- so it's safe to
    call from any thread and trivial to unit test without audio.
    """
    stripped = text.strip()
    if not stripped:
        return ""

    normalized = " ".join(_normalize(stripped).split())
    if not normalized:
        # No actual words at all -- just punctuation/symbols (e.g. a stray
        # "...", "--"). That's the issue's "stray ellipsis" case.
        return f"non-verbal junk: {stripped!r}"

    if normalized in JUNK_PHRASES:
        return f"matches known junk phrase: {normalized!r}"

    match = _REPEAT_LOOP_RE.search(normalized)
    if match:
        return f"repeated phrase: {match.group(1)!r}"

    return ""


class HallucinationFlaggerPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="hallucination_flagger",
        name=_("Hallucination Flagger"),
        description=_(
            "Flags segments that look hallucinated -- known silence junk "
            "phrases, or a word/phrase repeating 3+ times in a row -- so "
            "you can review them. Never deletes or edits the text."
        ),
        version="1.0.0",
        pip_dependencies=[],
        config_fields=[],
    )

    def after_transcription(
        self,
        task,
        segments: List[Segment],
        context: PluginContext,
    ) -> List[Segment]:
        for segment in segments:
            reason = check(segment.text)
            if reason:
                segment.metadata.append(
                    {"suspect": "true", "suspect_reason": reason}
                )
                context.log.debug("Flagged segment %r: %s", segment.text, reason)
        return segments
