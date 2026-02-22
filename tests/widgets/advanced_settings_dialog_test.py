import pytest
from pytestqt.qtbot import QtBot

from buzz.transcriber.transcriber import TranscriptionOptions
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog


class TestAdvancedSettingsDialogSilenceThreshold:
    def test_silence_threshold_spinbox_hidden_by_default(self, qtbot: QtBot):
        """Silence threshold UI is not shown when show_recording_settings=False."""
        options = TranscriptionOptions()
        dialog = AdvancedSettingsDialog(transcription_options=options)
        qtbot.add_widget(dialog)
        assert not hasattr(dialog, "silence_threshold_spin_box")

    def test_silence_threshold_spinbox_shown_when_recording_settings(self, qtbot: QtBot):
        """Silence threshold spinbox is present when show_recording_settings=True."""
        options = TranscriptionOptions()
        dialog = AdvancedSettingsDialog(
            transcription_options=options, show_recording_settings=True
        )
        qtbot.add_widget(dialog)
        assert hasattr(dialog, "silence_threshold_spin_box")
        assert dialog.silence_threshold_spin_box is not None

    def test_silence_threshold_spinbox_initial_value(self, qtbot: QtBot):
        """Spinbox reflects the current silence_threshold from options."""
        options = TranscriptionOptions(silence_threshold=0.0075)
        dialog = AdvancedSettingsDialog(
            transcription_options=options, show_recording_settings=True
        )
        qtbot.add_widget(dialog)
        assert dialog.silence_threshold_spin_box.value() == pytest.approx(0.0075)

    def test_silence_threshold_change_updates_options(self, qtbot: QtBot):
        """Changing spinbox value updates transcription_options.silence_threshold."""
        options = TranscriptionOptions(silence_threshold=0.0025)
        dialog = AdvancedSettingsDialog(
            transcription_options=options, show_recording_settings=True
        )
        qtbot.add_widget(dialog)
        dialog.silence_threshold_spin_box.setValue(0.005)
        assert dialog.transcription_options.silence_threshold == pytest.approx(0.005)

    def test_silence_threshold_change_emits_signal(self, qtbot: QtBot):
        """Changing the spinbox emits transcription_options_changed."""
        options = TranscriptionOptions(silence_threshold=0.0025)
        dialog = AdvancedSettingsDialog(
            transcription_options=options, show_recording_settings=True
        )
        qtbot.add_widget(dialog)

        emitted = []
        dialog.transcription_options_changed.connect(lambda o: emitted.append(o))

        dialog.silence_threshold_spin_box.setValue(0.005)

        assert len(emitted) == 1
        assert emitted[0].silence_threshold == pytest.approx(0.005)


class TestTranscriptionOptionsSilenceThreshold:
    def test_default_silence_threshold(self):
        options = TranscriptionOptions()
        assert options.silence_threshold == pytest.approx(0.0025)

    def test_custom_silence_threshold(self):
        options = TranscriptionOptions(silence_threshold=0.01)
        assert options.silence_threshold == pytest.approx(0.01)
