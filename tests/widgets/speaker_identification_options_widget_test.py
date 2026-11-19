from unittest.mock import Mock

from PyQt6.QtCore import QSettings

from buzz.widgets.transcriber.speaker_identification_options_widget import (
    SpeakerIdentificationOptions,
    SpeakerIdentificationOptionsWidget,
)


def make_settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


class TestSpeakerIdentificationOptions:
    def test_save_and_load(self, tmp_path):
        settings = make_settings(tmp_path)
        options = SpeakerIdentificationOptions(
            identify_speakers=True,
            speaker_diarizer="sortformer",
            speaker_count=4,
            merge_speaker_sentences=False,
        )
        options.save(settings)
        settings.sync()

        assert SpeakerIdentificationOptions.load(make_settings(tmp_path)) == options

    def test_load_defaults(self, tmp_path):
        assert (
            SpeakerIdentificationOptions.load(make_settings(tmp_path))
            == SpeakerIdentificationOptions()
        )

    def test_load_ignores_invalid_values(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.setValue("speaker_diarizer", "unknown")
        settings.setValue("speaker_count", "many")

        options = SpeakerIdentificationOptions.load(settings)

        assert options.speaker_diarizer == "msdd"
        assert options.speaker_count is None

    def test_save_auto_speaker_count(self, tmp_path):
        settings = make_settings(tmp_path)
        SpeakerIdentificationOptions(speaker_count=None).save(settings)

        assert SpeakerIdentificationOptions.load(settings).speaker_count is None


class TestSpeakerIdentificationOptionsWidget:
    def test_options_are_enabled_only_when_identifying_speakers(self, qtbot):
        widget = SpeakerIdentificationOptionsWidget(SpeakerIdentificationOptions())
        qtbot.add_widget(widget)
        changed = Mock()
        widget.options_changed.connect(changed)

        assert not widget.identify_speakers_checkbox.isChecked()
        assert not widget.diarizer_combo_box.isEnabled()
        assert not widget.speaker_count_combo_box.isEnabled()
        assert not widget.merge_speaker_sentences_checkbox.isEnabled()

        widget.identify_speakers_checkbox.setChecked(True)

        assert widget.diarizer_combo_box.isEnabled()
        assert widget.speaker_count_combo_box.isEnabled()
        assert widget.merge_speaker_sentences_checkbox.isEnabled()
        assert changed.call_args[0][0] == SpeakerIdentificationOptions(
            identify_speakers=True
        )

        widget.speaker_count_combo_box.setCurrentIndex(
            widget.speaker_count_combo_box.findData(3)
        )
        assert changed.call_args[0][0].speaker_count == 3

        widget.merge_speaker_sentences_checkbox.setChecked(False)
        assert changed.call_args[0][0].merge_speaker_sentences is False

        # The speaker count is an MSDD-only option
        widget.diarizer_combo_box.setCurrentIndex(
            widget.diarizer_combo_box.findData("sortformer")
        )
        assert changed.call_args[0][0].speaker_diarizer == "sortformer"
        assert not widget.speaker_count_combo_box.isEnabled()

    def test_shows_given_options(self, qtbot):
        options = SpeakerIdentificationOptions(
            identify_speakers=True,
            speaker_diarizer="msdd",
            speaker_count=5,
            merge_speaker_sentences=False,
        )
        widget = SpeakerIdentificationOptionsWidget(options)
        qtbot.add_widget(widget)

        assert widget.identify_speakers_checkbox.isChecked()
        assert widget.diarizer_combo_box.currentData() == "msdd"
        assert widget.speaker_count_combo_box.currentData() == 5
        assert not widget.merge_speaker_sentences_checkbox.isChecked()

        # Changes do not alter the options it was given
        widget.identify_speakers_checkbox.setChecked(False)
        assert options.identify_speakers is True

    def test_set_options_enabled(self, qtbot):
        widget = SpeakerIdentificationOptionsWidget(
            SpeakerIdentificationOptions(identify_speakers=True)
        )
        qtbot.add_widget(widget)

        widget.set_options_enabled(False)
        assert not widget.identify_speakers_checkbox.isEnabled()
        assert not widget.diarizer_combo_box.isEnabled()

        widget.set_options_enabled(True)
        assert widget.identify_speakers_checkbox.isEnabled()
        assert widget.diarizer_combo_box.isEnabled()
