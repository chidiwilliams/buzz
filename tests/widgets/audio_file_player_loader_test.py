from unittest.mock import MagicMock

from pytestqt.qtbot import QtBot

from buzz.widgets.audio_file_player_loader import AudioFilePlayerLoader
from tests.audio import test_audio_path


class TestAudioFilePlayerLoader:
    def test_loads_player(self, qtbot: QtBot):
        loader = AudioFilePlayerLoader(test_audio_path)

        with qtbot.wait_signal(loader.loaded, timeout=30_000) as blocker:
            loader.start()

        player = blocker.args[0]
        try:
            assert player.ready
            assert player.duration_ms > 0
        finally:
            player.close()
        qtbot.wait_until(lambda: loader not in AudioFilePlayerLoader._running)

    def test_reports_undecodable_file(self, qtbot: QtBot, tmp_path):
        not_audio = tmp_path / "notes.mp3"
        not_audio.write_text("not audio")
        loader = AudioFilePlayerLoader(str(not_audio))

        with qtbot.wait_signal(loader.loaded, timeout=30_000) as blocker:
            loader.start()

        assert blocker.args == [None]

    def test_cancelled_loader_does_not_report(self, qtbot: QtBot):
        loader = AudioFilePlayerLoader(test_audio_path)
        loaded = []
        loader.loaded.connect(loaded.append)

        loader.start()
        loader.cancel()

        qtbot.wait_until(lambda: loader not in AudioFilePlayerLoader._running)
        assert loaded == []

    def test_cancel_all_stops_running_loaders(self, qtbot: QtBot):
        loader = AudioFilePlayerLoader(test_audio_path)
        loader.start()

        AudioFilePlayerLoader.cancel_all()

        assert loader.isFinished()

    def test_player_decoded_before_cancel_is_dropped(self, qtbot: QtBot):
        """A player decoded just before cancelling is closed rather than delivered."""
        loader = AudioFilePlayerLoader(test_audio_path)
        loaded = []
        loader.loaded.connect(loaded.append)
        player = MagicMock()

        loader.cancel()
        loader._on_decoded(player)

        assert loaded == []
        player.close.assert_called_once()
