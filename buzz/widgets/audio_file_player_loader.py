import logging
from typing import Optional, Set

from PyQt6.QtCore import QThread, pyqtSignal, QCoreApplication

from buzz.sounddevice_player import AudioDecoder, AudioFilePlayer


class AudioFilePlayerLoader(QThread):
    """
    Creates an AudioFilePlayer on a background thread. Decoding takes a few
    seconds for long files, which would otherwise keep the player's window
    from opening.
    """

    # The AudioFilePlayer, or None when the file could not be decoded
    loaded = pyqtSignal(object)

    # Loaders are not parented to the widget that starts them, because Qt
    # aborts when a running thread is destroyed along with its parent. Keep
    # them referenced here until they finish instead.
    _running: Set["AudioFilePlayerLoader"] = set()
    _quit_hooked = False

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._decoder = AudioDecoder(file_path)
        self._cancelled = False
        self.finished.connect(self._on_finished)

    def start(self, priority=QThread.Priority.InheritPriority):
        AudioFilePlayerLoader._running.add(self)
        AudioFilePlayerLoader._hook_app_quit()
        super().start(priority)

    def run(self):
        player: Optional[AudioFilePlayer] = AudioFilePlayer(
            self.file_path, decoder=self._decoder
        )
        if self._cancelled or not player.ready:
            player.close()
            player = None
        if not self._cancelled:
            self.loaded.emit(player)

    def cancel(self):
        """Stops decoding. `loaded` is not emitted after this."""
        self._cancelled = True
        self._decoder.cancel()

    def _on_finished(self):
        AudioFilePlayerLoader._running.discard(self)

    @classmethod
    def _hook_app_quit(cls):
        app = QCoreApplication.instance()
        if cls._quit_hooked or app is None:
            return
        app.aboutToQuit.connect(cls.cancel_all)
        cls._quit_hooked = True

    @classmethod
    def cancel_all(cls):
        """Cancels and waits for every running loader, so none outlives the app."""
        for loader in list(cls._running):
            loader.cancel()
            if not loader.wait(5_000):
                logging.warning(
                    "Audio loader for %s did not stop", loader.file_path)
