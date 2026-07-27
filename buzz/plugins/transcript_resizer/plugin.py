"""
Automatic transcript resizer plugin for Buzz.

When a transcription is produced with word-level timings, this plugin
regroups the word-level segments into properly sized subtitles and replaces
the transcription with the result. It mirrors the "Merge" behaviour of
``buzz/widgets/transcription_viewer/transcription_resizer_widget.py`` but runs
automatically after every transcription.

Heavy imports (stable_whisper, srt_equalizer) are deferred to the hook so they
don't slow application startup.
"""

import logging
import os
import re

from buzz.plugins.base import (
    BuzzPlugin,
    ConfigField,
    ConfigFieldType,
    PluginContext,
    PluginMetadata,
    plugin_gettext,
)

logger = logging.getLogger(__name__)

_ = plugin_gettext(__file__)

# Matches a segment whose text ends with sentence-ending punctuation.
SENTENCE_END = re.compile(r".*[.!?。！？]")

# Languages that don't use spaces between words.
NON_SPACE_LANGUAGES = {"zh", "ja", "th", "lo", "km", "my"}

DEFAULT_PUNCTUATION = ".* /./. /。/?/? /？/!/! /！/,/, "


class TranscriptResizerPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="transcript_resizer",
        name=_("Automatic Transcript Resizer"),
        description=_(
            "When a transcription has word-level timings, automatically regroup "
            "the words into properly sized subtitles and replace the result. "
            "Mirrors the Merge options of the transcript resizer."
        ),
        version="1.0.0",
        pip_dependencies=[],
        config_fields=[
            ConfigField(
                key="merge_by_gap",
                label=_("Merge by gap"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="merge_gap_seconds",
                label=_("Merge gap (seconds)"),
                type=ConfigFieldType.TEXT,
                default="0.2",
            ),
            ConfigField(
                key="split_by_punctuation",
                label=_("Split by punctuation"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="punctuation",
                label=_("Punctuation"),
                type=ConfigFieldType.TEXT,
                default=DEFAULT_PUNCTUATION,
            ),
            ConfigField(
                key="split_by_max_length",
                label=_("Split by max length"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="max_length",
                label=_("Maximum subtitle length"),
                type=ConfigFieldType.TEXT,
                default="42",
            ),
        ],
    )

    def on_complete(self, transcription_id, task, segments, context: PluginContext):
        options = getattr(task, "transcription_options", None)
        word_level = bool(getattr(options, "word_level_timings", False))
        if not word_level:
            context.log.info(
                "Transcript resizer skipped: word-level timings not enabled"
            )
            return

        regroup_string = self._build_regroup_string(context.config)
        if not regroup_string:
            context.log.info("Transcript resizer skipped: no merge options enabled")
            return

        audio_path = self._resolve_audio_path(task)
        if audio_path is None:
            context.log.warning(
                "Transcript resizer skipped: source audio file not found"
            )
            return

        language = getattr(options, "language", None) or ""

        new_segments = self._regroup(
            transcription_id, audio_path, language, regroup_string, context
        )
        if not new_segments:
            context.log.info("Transcript resizer produced no segments; keeping original")
            return

        context.transcription_service.replace_transcription_segments(
            transcription_id, new_segments
        )
        context.log.info(
            "Transcript resizer replaced transcription with %d segments",
            len(new_segments),
        )

    def _build_regroup_string(self, cfg) -> str:
        merge_by_gap = _coerce_bool(cfg.get("merge_by_gap", True))
        split_by_punctuation = _coerce_bool(cfg.get("split_by_punctuation", True))
        split_by_max_length = _coerce_bool(cfg.get("split_by_max_length", True))
        gap = (cfg.get("merge_gap_seconds") or "0.2").strip()
        punctuation = cfg.get("punctuation") or DEFAULT_PUNCTUATION
        max_length = (cfg.get("max_length") or "42").strip()

        regroup_string = ""
        if merge_by_gap:
            regroup_string += f"mg={gap}"
            if split_by_max_length:
                regroup_string += f"++{max_length}+1"
        if split_by_punctuation:
            if regroup_string:
                regroup_string += "_"
            regroup_string += f"sp={punctuation}"
        if split_by_max_length:
            if regroup_string:
                regroup_string += "_"
            regroup_string += f"sl={max_length}"

        return os.getenv("BUZZ_MERGE_REGROUP_RULE", regroup_string)

    def _resolve_audio_path(self, task):
        # Prefer the original source file. When "Extract speech" is enabled,
        # task.file_path points at a temporary "_speech.mp3" that Buzz deletes
        # once the transcription completes, so it is already gone by the time
        # this hook runs. original_file_path holds the real source, which is
        # stable and shares the same timeline (regrouping runs with VAD and
        # silence suppression off, so it does not need the trimmed audio).
        candidates = [
            getattr(task, "original_file_path", None),
            getattr(task, "file_path", None),
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    def _regroup(self, transcription_id, audio_path, language, regroup_string, context):
        import stable_whisper

        from buzz import whisper_audio
        from buzz.transcriber.transcriber import Segment

        is_non_space = language in NON_SPACE_LANGUAGES
        separator = "" if is_non_space else " "

        def get_transcript(audio, **kwargs) -> dict:
            buzz_segments = context.transcription_service.get_transcription_segments(
                transcription_id=transcription_id
            )
            segments = []
            words = []
            text = ""
            for buzz_segment in buzz_segments:
                words.append(
                    {
                        "word": buzz_segment.text + separator,
                        "start": buzz_segment.start_time / 1000,
                        "end": buzz_segment.end_time / 1000,
                    }
                )
                text += buzz_segment.text + separator
                if SENTENCE_END.match(buzz_segment.text):
                    segments.append({"text": text, "words": words})
                    words = []
                    text = ""
            if words:
                segments.append({"text": text, "words": words})
            return {"language": language, "segments": segments}

        try:
            result = stable_whisper.transcribe_any(
                get_transcript,
                audio=whisper_audio.load_audio(audio_path),
                input_sr=whisper_audio.SAMPLE_RATE,
                vad=False,
                suppress_silence=False,
                regroup=regroup_string,
                check_sorted=False,
            )
        except Exception as exc:
            context.log.error("Transcript resizer regroup failed: %s", exc)
            return []

        return [
            Segment(
                start=int(segment.start * 1000),
                end=int(segment.end * 1000),
                text=segment.text,
            )
            for segment in result.segments
        ]


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
