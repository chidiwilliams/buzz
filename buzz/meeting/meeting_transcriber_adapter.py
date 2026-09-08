"""Qt adapter wrapping FileTranscriber for meeting final transcription.

Owns one concrete FileTranscriber lifecycle on a QThread.
Returns pure segment DTOs to the caller thread via Qt signals.
"""

from __future__ import annotations

import logging
from threading import Event, Thread
from time import monotonic
from typing import Optional

from PyQt6.QtCore import (
    QMetaObject,
    QObject,
    QThread,
    QTimer,
    Qt,
    pyqtSignal,
    pyqtSlot,
)

from buzz.meeting.final_transcription import (
    FinalTranscriptionConfig,
    TrackTranscriptionInputSegment,
    TrackTranscriptionInputWord,
    TrackTranscriptionResult,
)
from buzz.model_loader import ModelType, TranscriptionModel, WhisperModelSize
from buzz.transcriber.transcriber import (
    DEFAULT_WHISPER_TEMPERATURE,
    FileTranscriptionOptions,
    FileTranscriptionTask,
    Segment,
    Task,
    TranscriptionOptions,
)
from buzz.transcriber.whisper_file_transcriber import (
    DetailedWhisperFileTranscriber,
    WhisperFileTranscriber,
)

logger = logging.getLogger(__name__)

# Parent destruction must not delete a running QThread after a failed shutdown.
# Entries are removed only after verified worker destruction and a joined thread.
_owned_workers: set[tuple[QThread, WhisperFileTranscriber]] = set()


class MeetingTrackTranscriber(QObject):
    """Run FileTranscriber for one meeting track on a dedicated QThread.

    Emits ``track_completed`` with pure segment DTOs or ``track_error``
    with an error message.  Uses ``WhisperFileTranscriber`` only — no
    OpenAI API backend in PR11.

    Usage::

        adapter = MeetingTrackTranscriber()
        adapter.track_completed.connect(my_handler)
        adapter.start(audio_path, sample_rate, config)
        # ...
        adapter.shutdown()
    """

    track_completed = pyqtSignal(object)  # list[TrackTranscriptionInputSegment]
    track_rich_completed = pyqtSignal(object)  # TrackTranscriptionResult
    track_error = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._transcriber: Optional[WhisperFileTranscriber] = None
        self._thread: Optional[QThread] = None
        self._shutdown_requested = False
        self._active_profile_version: Optional[int] = None
        self._stop_thread: Optional[Thread] = None
        self._worker_destroyed = Event()
        self._dispose_requested = False
        self._pending_result = None

    def start(
        self,
        audio_path: str,
        sample_rate: int,
        config: FinalTranscriptionConfig,
    ) -> None:
        """Start transcription of one audio file.

        Constructs a FileTranscriptionTask with fixed profile semantics.
        """
        if self._shutdown_requested:
            self.track_error.emit("Shutdown requested")
            return

        if self._transcriber is not None:
            self.track_error.emit("Transcriber already active")
            return

        # Resolve model path from persisted config
        model_type = self._resolve_model_type(config.model_type)
        whisper_size = self._resolve_whisper_size(config.whisper_model_size)
        model = TranscriptionModel(
            model_type=model_type,
            whisper_model_size=whisper_size,
            hugging_face_model_id=config.hugging_face_model_id or "",
        )
        model_path = model.get_local_model_path()
        if model_path is None:
            self.track_error.emit(
                f"Model not available locally: {config.model_type}/"
                f"{config.whisper_model_size or config.hugging_face_model_id}"
            )
            return

        task = self._build_task(str(audio_path), config, model, model_path)

        transcriber_class = (
            DetailedWhisperFileTranscriber
            if config.profile_version == 2
            else WhisperFileTranscriber
        )
        self._transcriber = transcriber_class(task=task)
        self._active_profile_version = config.profile_version
        self._thread = QThread()
        self._worker_destroyed.clear()
        self._dispose_requested = False
        _owned_workers.add((self._thread, self._transcriber))
        self._transcriber.moveToThread(self._thread)

        # Wire signals
        self._thread.started.connect(self._transcriber.run)
        self._transcriber.completed.connect(self._on_completed)
        self._transcriber.error.connect(self._on_error)
        self._transcriber.completed.connect(
            self._transcriber.dispose_in_owner_thread,
            Qt.ConnectionType.DirectConnection,
        )
        self._transcriber.error.connect(
            self._transcriber.dispose_in_owner_thread,
            Qt.ConnectionType.DirectConnection,
        )
        self._transcriber.destroyed.connect(
            self._worker_destroyed.set, Qt.ConnectionType.DirectConnection
        )
        self._transcriber.destroyed.connect(
            self._thread.quit, Qt.ConnectionType.DirectConnection
        )
        self._thread.finished.connect(self._on_thread_finished)

        self._thread.start()

    def shutdown(self, timeout_ms: int = 10000) -> bool:
        """Cancel permanently and wait at most timeout_ms for owned workers.

        True verifies backend cleanup, worker destruction on its owning Qt
        thread, and a joined QThread. False retains ownership for a later retry.
        Durable meeting state is left untouched. Call on the adapter's Qt thread.
        """
        if timeout_ms < 0:
            raise ValueError("timeout_ms must be non-negative")
        deadline = monotonic() + timeout_ms / 1000
        self._shutdown_requested = True

        transcriber = self._transcriber
        thread = self._thread
        if transcriber is None:
            return thread is None

        if not self._worker_destroyed.is_set():
            transcriber.request_cancel()

            def stop():
                try:
                    transcriber.stop()
                except Exception:
                    logger.exception("Error stopping transcriber")

            if self._stop_thread is None or not self._stop_thread.is_alive():
                self._stop_thread = Thread(
                    target=stop, name="meeting-transcription-stop"
                )
                try:
                    self._stop_thread.start()
                except Exception:
                    logger.exception("Could not start transcriber cleanup")
                    return False

            self._stop_thread.join(max(0, deadline - monotonic()))
            if self._stop_thread.is_alive():
                return False
            if not transcriber.cleanup_complete and not transcriber.wait_for_cleanup(
                max(0, deadline - monotonic())
            ):
                return False

            if not self._worker_destroyed.is_set() and not self._dispose_requested:
                self._dispose_requested = True
                try:
                    QMetaObject.invokeMethod(
                        transcriber,
                        "dispose_in_owner_thread",
                        Qt.ConnectionType.QueuedConnection,
                    )
                except RuntimeError:
                    self._dispose_requested = False
                    if not self._worker_destroyed.is_set():
                        return False

            if not self._worker_destroyed.wait(max(0, deadline - monotonic())):
                return False

        if thread is None or not thread.wait(
            max(0, int((deadline - monotonic()) * 1000))
        ):
            return False

        self._release_worker()
        return True

    def _release_worker(self) -> None:
        """Release Python ownership only after destruction and QThread join."""
        if self._thread is not None:
            if not self._worker_destroyed.is_set() or not self._thread.wait(0):
                raise RuntimeError("Worker ownership released before verified shutdown")
            _owned_workers.discard((self._thread, self._transcriber))
            self._thread.deleteLater()
        self._transcriber = None
        self._thread = None
        self._stop_thread = None
        self._active_profile_version = None
        self._pending_result = None

    @pyqtSlot()
    def _on_thread_finished(self) -> None:
        if self._shutdown_requested or self._thread is None:
            return
        if not self._worker_destroyed.is_set() or not self._thread.wait(0):
            QTimer.singleShot(1, self._on_thread_finished)
            return
        pending = self._pending_result
        if pending is None:
            QTimer.singleShot(1, self._on_thread_finished)
            return
        kind, value, profile_version, detailed_words = pending
        self._release_worker()
        if kind == "completed":
            self._emit_completed(value, profile_version, detailed_words)
        else:
            self.track_error.emit(value)

    @pyqtSlot(list)
    def _on_completed(self, segments: list[Segment]) -> None:
        if self._shutdown_requested:
            return  # Suppress callback during intentional shutdown
        profile_version = self._active_profile_version
        detailed_words = (
            tuple(self._transcriber.detailed_words)
            if profile_version == 2 and self._transcriber is not None
            else ()
        )
        if self._thread is None:
            self._transcriber = None
            self._active_profile_version = None
            self._emit_completed(segments, profile_version, detailed_words)
            return
        self._pending_result = (
            "completed",
            segments,
            profile_version,
            detailed_words,
        )

    def _emit_completed(
        self,
        segments: list[Segment],
        profile_version: Optional[int],
        detailed_words: tuple,
    ) -> None:
        """Convert backend output after verified worker destruction and join."""
        if profile_version == 2:
            result = TrackTranscriptionResult(
                segments=tuple(
                    TrackTranscriptionInputSegment(
                        start_ms=seg.start,
                        end_ms=seg.end,
                        text=seg.text,
                    )
                    for seg in segments
                ),
                words=tuple(
                    TrackTranscriptionInputWord(
                        source_segment_ordinal=word.source_segment_ordinal,
                        start_ms=word.start_ms,
                        end_ms=word.end_ms,
                        text=word.text,
                    )
                    for word in detailed_words
                ),
            )
            self.track_rich_completed.emit(result)
        else:
            self.track_completed.emit(
                [
                    TrackTranscriptionInputSegment(
                        start_ms=seg.start,
                        end_ms=seg.end,
                        text=seg.text,
                    )
                    for seg in segments
                ]
            )

    @pyqtSlot(str)
    def _on_error(self, error: str) -> None:
        """Queue an error until worker destruction and thread exit are verified."""
        if self._shutdown_requested:
            return  # Suppress callback during intentional shutdown
        if self._thread is None:
            self._transcriber = None
            self._active_profile_version = None
            self.track_error.emit(error)
            return
        self._pending_result = ("error", error, None, ())

    @staticmethod
    def _resolve_model_type(model_type_str: str) -> ModelType:
        """Convert persisted model_type string to ModelType enum."""
        mapping = {
            "WHISPER": ModelType.WHISPER,
            "WHISPER_CPP": ModelType.WHISPER_CPP,
            "FASTER_WHISPER": ModelType.FASTER_WHISPER,
            "HUGGING_FACE": ModelType.HUGGING_FACE,
        }
        result = mapping.get(model_type_str)
        if result is None:
            raise ValueError(f"Unsupported model_type: {model_type_str!r}")
        return result

    @staticmethod
    def _resolve_whisper_size(
        size_str: Optional[str],
    ) -> Optional[WhisperModelSize]:
        """Convert persisted whisper_model_size string to enum."""
        if size_str is None:
            return None
        try:
            return WhisperModelSize[size_str]
        except KeyError:
            raise ValueError(f"Unknown whisper_model_size: {size_str!r}")

    @staticmethod
    def _build_task(
        audio_path: str,
        config: FinalTranscriptionConfig,
        model: TranscriptionModel,
        model_path: str,
    ) -> FileTranscriptionTask:
        """Build a task containing only the frozen profile semantics."""
        transcription_options = TranscriptionOptions(
            language=config.language,
            task=Task.TRANSCRIBE,
            model=model,
            word_level_timings=config.profile_version == 2,
            extract_speech=False,
            temperature=DEFAULT_WHISPER_TEMPERATURE,
            initial_prompt="",
            openai_access_token="",
            enable_llm_translation=False,
            silence_threshold=0.0025,
        )
        return FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=FileTranscriptionOptions(
                file_paths=None,
                url=None,
                output_formats=set(),
            ),
            model_path=model_path,
            file_path=audio_path,
            source=FileTranscriptionTask.Source.FILE_IMPORT,
            delete_source_file=False,
        )


__all__ = ["MeetingTrackTranscriber"]
