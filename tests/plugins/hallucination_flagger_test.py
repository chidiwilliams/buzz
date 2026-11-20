import json

from buzz.plugins.base import HIGHLIGHT_METADATA_KEY, RESERVED_METADATA_KEYS
from buzz.plugins.hallucination_flagger.plugin import (
    HallucinationFlaggerPlugin,
    check,
)
from buzz.transcriber.transcriber import Segment


class TestCheck:
    def test_flags_known_junk_phrase(self):
        assert check("Thanks for watching!") != ""
        assert check("[Music]") != ""
        assert check("(Applause)") != ""
        assert check("  thanks   for watching  ") != ""

    def test_does_not_flag_real_sentence_containing_junk_words(self):
        # Contains "music" and "subscribe" but isn't an exact match against
        # the whole segment -- should not be flagged.
        assert check("I turned on some music while I subscribed to the gym.") == ""

    def test_flags_stray_punctuation_only_segment(self):
        assert check("...") != ""
        assert check("--") != ""

    def test_flags_repeated_word_loop(self):
        assert check("the the the") != ""
        assert check("okay okay okay okay") != ""

    def test_flags_repeated_short_phrase_loop(self):
        assert (
            check("I don't know I don't know I don't know what happened") != ""
        )

    def test_flags_repeated_phrase_separated_by_punctuation(self):
        # One of the most common real Whisper loops: the repeats are their
        # own sentences, not bare whitespace-joined tokens.
        assert check("Thank you. Thank you. Thank you. Thank you.") != ""

    def test_does_not_flag_short_repetition(self):
        # Only two repeats -- below the 3+ threshold.
        assert check("very very good") == ""

    def test_does_not_flag_normal_sentence(self):
        assert check("The weather today is sunny with a light breeze.") == ""

    def test_empty_text_is_not_flagged(self):
        assert check("") == ""
        assert check("   ") == ""


class TestHallucinationFlaggerPlugin:
    def test_after_transcription_flags_only_suspect_segments(self):
        plugin = HallucinationFlaggerPlugin()
        segments = [
            Segment(0, 1000, "Thanks for watching!"),
            Segment(1000, 2000, "The weather today is sunny."),
            Segment(2000, 3000, "no no no no"),
        ]

        result = plugin.after_transcription(task=None, segments=segments, context=_FakeContext())

        assert result is segments
        assert segments[0].metadata and segments[0].metadata[0]["suspect"] == "true"
        assert segments[1].metadata == []
        assert segments[2].metadata and segments[2].metadata[0]["suspect"] == "true"

    def test_metadata_id_matches_folder_name(self):
        assert HallucinationFlaggerPlugin.metadata.id == "hallucination_flagger"

    def test_flag_requests_a_row_highlight(self):
        """Without this the flag is tooltip-only and easy to miss."""
        segment = Segment(0, 1000, "Thanks for watching!")

        HallucinationFlaggerPlugin().after_transcription(
            task=None, segments=[segment], context=_FakeContext()
        )

        assert segment.metadata[0][HIGHLIGHT_METADATA_KEY] == "warning"

    def test_reason_is_readable_without_relying_on_the_colour(self):
        """Colour must never be the only thing carrying the meaning."""
        segment = Segment(0, 1000, "Thanks for watching!")

        HallucinationFlaggerPlugin().after_transcription(
            task=None, segments=[segment], context=_FakeContext()
        )

        reason = segment.metadata[0]["suspect_reason"]
        assert reason and reason not in RESERVED_METADATA_KEYS


class TestBundling:
    """A bundled plugin must be registered and fully localized (AGENTS.md)."""

    def test_is_registered_as_a_bundled_plugin(self):
        from buzz.plugins import loader

        assert "hallucination_flagger" in loader.BUNDLED_PLUGIN_IDS

    def test_ships_the_same_locale_set_as_other_bundled_plugins(self):
        import os

        locales = os.listdir("buzz/plugins/hallucination_flagger/locale")
        reference = os.listdir("buzz/plugins/ai_summary/locale")
        assert set(locales) == set(reference)

    def test_every_locale_translates_both_strings(self):
        """An absent key or empty value silently blanks or un-translates the UI.

        Asserts against the literal English sources rather than
        ``metadata.name``/``.description``, which are already translated when
        the suite runs under a non-English locale.
        """
        import glob
        import os

        sources = (
            "Hallucination Flagger",
            "Flags transcript segments that look hallucinated so you can "
            "review them. Never deletes or changes the text.",
        )
        for path in glob.glob("buzz/plugins/hallucination_flagger/locale/*.json"):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for source in sources:
                assert source in data, f"{os.path.basename(path)} missing a key"
                assert data[source].strip(), f"{os.path.basename(path)} has an empty value"


def test_flag_metadata_survives_the_database_round_trip(
    qtbot, transcription_service, transcription_dao
):
    """The flag must reach the viewer, not just the in-memory Segment.

    The viewer reads tooltips from the persisted ``metadata`` column, so a
    flag that doesn't survive the Segment -> DB hop would be invisible to
    the user even though the hook "worked".
    """
    from buzz.transcriber.transcriber import (
        FileTranscriptionOptions,
        FileTranscriptionTask,
        TranscriptionOptions,
    )

    task = FileTranscriptionTask(
        file_path="/tmp/audio.mp3",
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(),
        model_path="mock_path",
    )
    transcription_service.create_transcription(task)

    segments = HallucinationFlaggerPlugin().after_transcription(
        task=task,
        segments=[
            Segment(0, 1000, "Thanks for watching!"),
            Segment(1000, 2000, "The weather today is sunny."),
        ],
        context=_FakeContext(),
    )
    transcription_service.update_transcription_as_completed(task.uid, segments)

    saved = sorted(
        transcription_service.get_transcription_segments(transcription_id=task.uid),
        key=lambda s: s.start_time,
    )
    flagged = json.loads(saved[0].metadata)
    assert flagged and flagged[0]["suspect"] == "true"
    assert "suspect_reason" in flagged[0]
    assert json.loads(saved[1].metadata) == []


class _FakeContext:
    """Minimal stand-in for PluginContext -- only `.log` is used by this hook."""

    class _Log:
        def debug(self, *args, **kwargs):
            pass

    log = _Log()
