import pytest
from pytestqt.qtbot import QtBot

from buzz.widgets.audio_meter_widget import AudioMeterWidget


class TestAudioMeterWidget:
    def test_initial_amplitude_is_zero(self, qtbot: QtBot):
        widget = AudioMeterWidget()
        qtbot.add_widget(widget)
        assert widget.current_amplitude == 0.0

    def test_initial_average_amplitude_is_zero(self, qtbot: QtBot):
        widget = AudioMeterWidget()
        qtbot.add_widget(widget)
        assert widget.average_amplitude == 0.0

    def test_update_amplitude(self, qtbot: QtBot):
        widget = AudioMeterWidget()
        qtbot.add_widget(widget)
        widget.update_amplitude(0.5)
        assert widget.current_amplitude == pytest.approx(0.5)

    def test_update_amplitude_smoothing(self, qtbot: QtBot):
        """Lower amplitude should decay via smoothing factor, not drop instantly."""
        widget = AudioMeterWidget()
        qtbot.add_widget(widget)
        widget.update_amplitude(1.0)
        widget.update_amplitude(0.0)
        # current_amplitude should be smoothed: max(0.0, 1.0 * SMOOTHING_FACTOR)
        assert widget.current_amplitude == pytest.approx(1.0 * widget.SMOOTHING_FACTOR)

    def test_update_average_amplitude(self, qtbot: QtBot):
        widget = AudioMeterWidget()
        qtbot.add_widget(widget)
        widget.update_average_amplitude(0.0123)
        assert widget.average_amplitude == pytest.approx(0.0123)

    def test_reset_amplitude_clears_current(self, qtbot: QtBot):
        widget = AudioMeterWidget()
        qtbot.add_widget(widget)
        widget.update_amplitude(0.8)
        widget.reset_amplitude()
        assert widget.current_amplitude == 0.0

    def test_reset_amplitude_clears_average(self, qtbot: QtBot):
        widget = AudioMeterWidget()
        qtbot.add_widget(widget)
        widget.update_average_amplitude(0.05)
        widget.reset_amplitude()
        assert widget.average_amplitude == 0.0

    def test_fixed_height(self, qtbot: QtBot):
        widget = AudioMeterWidget()
        qtbot.add_widget(widget)
        assert widget.height() == 56
