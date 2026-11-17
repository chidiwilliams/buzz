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


class _FakeContext:
    """Minimal stand-in for PluginContext -- only `.log` is used by this hook."""

    class _Log:
        def debug(self, *args, **kwargs):
            pass

    log = _Log()
