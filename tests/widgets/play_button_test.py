from pytestqt.qtbot import QtBot

from buzz.widgets.play_button import PlayButton


class TestPlayButton:
    def test_shows_no_progress_by_default(self, qtbot: QtBot):
        button = PlayButton()
        qtbot.add_widget(button)

        assert not button.showing_progress

    def test_spins_until_progress_is_known(self, qtbot: QtBot):
        button = PlayButton()
        qtbot.add_widget(button)

        button.start_progress()
        assert button.showing_progress
        assert button.progress is None
        assert button._spin_timer.isActive()

        button.set_progress(42)
        assert button.progress == 42
        assert not button._spin_timer.isActive()

    def test_stop_progress(self, qtbot: QtBot):
        button = PlayButton()
        qtbot.add_widget(button)
        button.start_progress()

        button.stop_progress()

        assert not button.showing_progress
        assert not button._spin_timer.isActive()

    def test_progress_is_clamped(self, qtbot: QtBot):
        button = PlayButton()
        qtbot.add_widget(button)

        button.set_progress(120)

        assert button.progress == 100

    def test_paints_progress(self, qtbot: QtBot):
        button = PlayButton()
        qtbot.add_widget(button)
        button.resize(40, 30)

        for start in (button.start_progress, lambda: button.set_progress(0),
                      lambda: button.set_progress(60)):
            start()
            assert not button.grab().isNull()
