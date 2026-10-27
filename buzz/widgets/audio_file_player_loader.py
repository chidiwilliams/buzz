import logging
import os
from typing import Optional, Set

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, QCoreApplication, QDeadlineTimer

from buzz.locale import _
from buzz.sounddevice_player import AudioDecoder, AudioFilePlayer


class AudioFilePlayerLoader(QThread):
    """
    Creates an AudioFilePlayer on a background thread. Decoding takes a few
    seconds for long files, which would otherwise keep the player's window
    from opening.
    """

    # The AudioFilePlayer, or None when the file could not be decoded
    loaded = pyqtSignal(object)
    # Percentage decoded, when the duration of the file is known
    progress = pyqtSignal(int)
    # After `loaded`, or instead of it when cancelled. Unlike QThread's
    # `finished`, it is emitted on the thread that owns the loader, so it
    # still reaches a slot connected once the thread has ended.
    done = pyqtSignal()
    # Emitted from run(), and handled on the thread that owns the loader
    _decoded = pyqtSignal(object)
    _progressed = pyqtSignal(int)

    # Loaders are not parented to the widget that starts them, because Qt
    # aborts when a running thread is destroyed along with its parent. Keep
    # them referenced here until they finish instead.
    _running: Set["AudioFilePlayerLoader"] = set()
    _quit_hooked = False

    def __init__(self, file_path: str, duration_s: Optional[float] = None):
        """`duration_s` is the audio's, if the file was probed already."""
        super().__init__()
        self.file_path = file_path
        self._percent = -1
        self._decoder = AudioDecoder(
            file_path, on_progress=self._report_progress, duration_s=duration_s)
        self._decoded.connect(self._on_decoded)
        self._progressed.connect(self._on_progressed)
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
        else:
            self.loaded.emit(player)
        self.done.emit()

    def _report_progress(self, fraction: float):
        # Called for every read from ffmpeg, so only pass on whole percents
        percent = int(fraction * 100)
        if percent != self._percent:
            self._percent = percent
            self._progressed.emit(percent)

    def _on_progressed(self, percent: int):
        if not self._decoder.cancelled:
            self.progress.emit(percent)

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
        loaders = list(cls._running)
        # All at once, so the others do not decode on while one is waited for
        for loader in loaders:
            loader.cancel()
        # One deadline for all, as each stuck one would delay quitting again.
        # A loader still running when the app exits does no harm: its run()
        # holds it, so it is not destroyed while running, which Qt aborts on.
        deadline = QDeadlineTimer(5_000)
        for loader in loaders:
            if not loader.wait(deadline):
                logging.warning(
                    "Audio loader for %s did not stop", loader.file_path)


class DecodedAudioMixin:
    """
    Decodes a player widget's audio in the background for sounddevice
    playback. The widget has a `play_button`, a PlayButton, and implements
    `_on_audio_loaded(sd_player)`, called with the AudioFilePlayer, or None
    when the file could not be decoded.
    """

    def _init_decoded_audio(self):
        self._sd_player: Optional[AudioFilePlayer] = None
        self._use_sd = False
        self._audio_loader: Optional[AudioFilePlayerLoader] = None

    @property
    def _loading_audio(self) -> bool:
        return self._audio_loader is not None

    def _start_audio_loader(self, file_path: str, duration_s: Optional[float] = None):
        """`duration_s` is the audio's, if the widget probed the file already."""
        # Playback waits for the decoded audio, which for a long file takes a
        # while. Spins until the duration of the file is known.
        self.play_button.setDisabled(True)
        self.play_button.setToolTip(_("Loading audio"))
        self.play_button.start_progress()
        self._audio_loader = AudioFilePlayerLoader(file_path, duration_s)
        self._audio_loader.progress.connect(self._show_audio_loading_progress)
        self._audio_loader.loaded.connect(self._receive_decoded_audio)
        self.destroyed.connect(self._audio_loader.cancel)
        self._audio_loader.start()

    def _show_audio_loading_progress(self, percent: int):
        self.play_button.set_progress(percent)

    def _receive_decoded_audio(self, sd_player: Optional[AudioFilePlayer]):
        file_path = self._audio_loader.file_path
        self._audio_loading_finished()
        if sd_player is None:
            # Otherwise the player is just disabled, without saying why. The
            # file of a URL import, for one, is in a temporary folder that the
            # system may clear.
            if os.path.isfile(file_path):
                self.play_button.setToolTip(_("Could not load audio"))
            else:
                self.play_button.setToolTip(_("Audio file not found: {}").format(file_path))
        self._on_audio_loaded(sd_player)

    def _cancel_audio_loader(self):
        if self._audio_loader is not None:
            self._audio_loader.cancel()
        self._audio_loading_finished()

    def _audio_loading_finished(self):
        self._audio_loader = None
        self.play_button.stop_progress()
        self.play_button.setToolTip("")

    def decoded_samples(self) -> Optional[np.ndarray]:
        """The decoded audio, for sharing with other players of the same file."""
        return self._sd_player.samples if self._sd_player is not None else None

    def audio_loader(self) -> Optional[AudioFilePlayerLoader]:
        """
        The loader decoding the audio, or None if it is not decoding. Others
        that need the same audio can wait for its `done` and then call
        decoded_samples(), rather than decoding the file again.
        """
        return self._audio_loader
