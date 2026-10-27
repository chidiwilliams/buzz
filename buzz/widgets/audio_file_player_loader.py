import logging
from typing import Optional, Set

import numpy as np
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
    # Emitted from run(), and handled on the thread that owns the loader
    _decoded = pyqtSignal(object)

    # Loaders are not parented to the widget that starts them, because Qt
    # aborts when a running thread is destroyed along with its parent. Keep
    # them referenced here until they finish instead.
    _running: Set["AudioFilePlayerLoader"] = set()
    _quit_hooked = False

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._decoder = AudioDecoder(file_path)
        self._decoded.connect(self._on_decoded)
        self.finished.connect(self._on_finished)

    def start(self, priority=QThread.Priority.InheritPriority):
        AudioFilePlayerLoader._running.add(self)
        AudioFilePlayerLoader._hook_app_quit()
        super().start(priority)

    def run(self):
        player = AudioFilePlayer(self.file_path, decoder=self._decoder)
        if not player.ready:
            player.close()
            player = None
        self._decoded.emit(player)

    def _on_decoded(self, player: Optional[AudioFilePlayer]):
        # Checked here rather than in run(), as cancel() is called on this
        # thread too: a player decoded just before cancelling is dropped
        # instead of reaching a widget that has already closed
        if self._decoder.cancelled:
            if player is not None:
                player.close()
            return
        self.loaded.emit(player)

    def cancel(self):
        """Stops decoding. `loaded` is not emitted after this."""
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


class DecodedAudioMixin:
    """
    Decodes a player widget's audio in the background for sounddevice
    playback. The widget has a `play_button` and implements
    `_on_audio_loaded(sd_player)`, called with the AudioFilePlayer, or None
    when the file could not be decoded.
    """

    def _init_decoded_audio(self):
        self._sd_player: Optional[AudioFilePlayer] = None
        self._use_sd = False
        self._loading_audio = False
        self._audio_loader: Optional[AudioFilePlayerLoader] = None

    def _start_audio_loader(self, file_path: str):
        # Playback waits for the decoded audio
        self._loading_audio = True
        self.play_button.setDisabled(True)
        self._audio_loader = AudioFilePlayerLoader(file_path)
        self._audio_loader.loaded.connect(self._receive_decoded_audio)
        self.destroyed.connect(self._audio_loader.cancel)
        self._audio_loader.start()

    def _receive_decoded_audio(self, sd_player: Optional[AudioFilePlayer]):
        self._loading_audio = False
        self._audio_loader = None
        self._on_audio_loaded(sd_player)

    def _cancel_audio_loader(self):
        if self._audio_loader is not None:
            self._audio_loader.cancel()
            self._audio_loader = None
        self._loading_audio = False

    def decoded_samples(self) -> Optional[np.ndarray]:
        """The decoded audio, for sharing with other players of the same file."""
        return self._sd_player.samples if self._sd_player is not None else None
