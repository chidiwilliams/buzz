"""
buzz/transcriber/bulk_renamer.py

Bulk-rename a folder of audio files based on the first few transcribed words
of each one. Reuses Buzz's existing offline transcription pipeline so no
internet connection or third-party API is required.

Pipeline per file
-----------------
1. Trim the first N seconds with ffmpeg into a small WAV file in a temp dir.
2. Run Buzz's WhisperFileTranscriber on that trimmed clip.
3. Take the first K words of the resulting text and sanitize into a filename.
4. Build a RenamePlan (pending) — nothing is renamed yet.

Renames are applied as a separate explicit step so the caller (CLI or GUI) can
preview, edit, or abort the whole batch atomically. Every applied batch writes
a JSON undo log to the source folder which can be used to reverse the rename.

Public API
----------
- ``RenamerConfig``           — configuration dataclass
- ``RenamePlan``              — one planned rename
- ``BulkRenamer``             — orchestrator with PyQt signals (preview/cancel)
- ``apply_plan``              — execute renames + write undo log
- ``undo_from_log``           — reverse a previously applied batch
- ``sanitize_filename``       — exposed for the dialog's inline edit
- ``first_n_words``

This module follows the same design as the existing Buzz transcribers: it
emits PyQt signals for progress, log lines, and completion so the GUI can
hook in cleanly. The transcription itself is delegated to
``WhisperFileTranscriber`` so we get all of Buzz's supported backends
(Whisper, Whisper.cpp, Faster-Whisper, HuggingFace) for free.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from buzz.assets import APP_BASE_DIR
from buzz.transcriber.transcriber import (
    FileTranscriptionOptions,
    FileTranscriptionTask,
    Segment,
    Task,
    TranscriptionOptions,
)
from buzz.transcriber.whisper_file_transcriber import WhisperFileTranscriber


DEFAULT_EXTENSIONS = (
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".opus",
)
DEFAULT_TRIM_SECONDS = 5.0
DEFAULT_FIRST_WORDS = 6
DEFAULT_MAX_FILENAME = 50

# Pull ffmpeg from the same place WhisperAudio does so we work both in
# development (system ffmpeg) and in the bundled app (vendored ffmpeg).
_APP_ENV = os.environ.copy()
_APP_ENV['PATH'] = os.pathsep.join(
    [os.path.join(APP_BASE_DIR, "_internal")] + [_APP_ENV['PATH']]
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RenamerConfig:
    """All knobs in one place."""
    transcription_options: TranscriptionOptions = field(
        default_factory=TranscriptionOptions
    )
    model_path: str = ""
    trim_seconds: float = DEFAULT_TRIM_SECONDS
    first_words: int = DEFAULT_FIRST_WORDS
    max_filename_len: int = DEFAULT_MAX_FILENAME
    extensions: tuple = DEFAULT_EXTENSIONS
    keep_numeric_prefix: bool = False
    collision_strategy: str = "suffix"   # 'suffix' or 'skip'


@dataclass
class RenamePlan:
    """One planned rename (not yet applied)."""
    original_path: Path
    transcript: str = ""
    proposed_name: str = ""
    proposed_path: Optional[Path] = None
    status: str = "pending"    # pending | ready | error | skipped | applied
    error: str = ""
    duration_sec: float = 0.0  # processing time

    @property
    def will_change(self) -> bool:
        return (
            self.status == "ready"
            and self.proposed_path is not None
            and self.proposed_path != self.original_path
        )


# ---------------------------------------------------------------------------
# Filename sanitation
# ---------------------------------------------------------------------------

_INVALID = re.compile(r'[^\w\s-]')
_WHITESPACE = re.compile(r'\s+')
_MULTI_UNDERSCORE = re.compile(r'_+')


def sanitize_filename(text: str, max_length: int = DEFAULT_MAX_FILENAME) -> str:
    """Convert free text into a filesystem-safe filename stem."""
    s = text.strip().lower()
    s = _INVALID.sub('', s)
    s = _WHITESPACE.sub('_', s)
    s = _MULTI_UNDERSCORE.sub('_', s)
    if len(s) > max_length:
        s = s[:max_length].rsplit('_', 1)[0]
    return s.strip('_')


def first_n_words(text: str, n: int) -> str:
    """Return the first N whitespace-separated tokens of `text`."""
    words = text.split()
    return ' '.join(words[:n]) if words else ''


# ---------------------------------------------------------------------------
# Audio trimming
# ---------------------------------------------------------------------------

class TrimError(RuntimeError):
    """Raised when the ffmpeg trim step fails for one file."""


def trim_to_temp_wav(audio_path: Path, seconds: float, out_dir: Path) -> Path:
    """Trim the first `seconds` of audio_path → mono 16 kHz WAV in out_dir.

    Returns the path to the new WAV file. The caller is responsible for
    cleaning up the file (or the containing temp dir).
    """
    out_path = out_dir / f"{audio_path.stem}_clip.wav"
    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-y",
        "-i", str(audio_path),
        "-t", f"{seconds:.3f}",
        "-vn",                  # drop any video / artwork stream
        "-ac", "1",             # mono
        "-ar", "16000",         # 16 kHz — matches Whisper's input rate
        str(out_path),
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            env=_APP_ENV,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        raise TrimError(
            f"ffmpeg failed for {audio_path.name}: "
            f"{e.stderr.decode(errors='ignore').strip()}"
        )
    except subprocess.TimeoutExpired:
        raise TrimError(f"ffmpeg timed out on {audio_path.name}")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TrimError(f"ffmpeg produced no output for {audio_path.name}")
    return out_path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class BulkRenamer(QObject):
    """Plan and apply bulk renames using Buzz's offline transcribers.

    Signals
    -------
    progress(int done, int total, RenamePlan plan)
        Emitted after each file's transcription completes.
    log(str message, str level)
        Emitted for human-readable status. ``level`` ∈ {'info','warn','error'}.
    finished(list[RenamePlan])
        Emitted once when ``plan_renames`` finishes (or is cancelled).

    Notes
    -----
    Transcription is sequential, not concurrent: the underlying
    ``WhisperFileTranscriber`` spins up a multiprocessing worker per file and
    Whisper itself is heavy on CPU/GPU, so running multiple transcriptions in
    parallel would just thrash. Buzz's existing `FileTranscriberQueueWorker`
    follows the same pattern.
    """

    progress = pyqtSignal(int, int, object)    # done, total, RenamePlan
    log = pyqtSignal(str, str)                  # message, level
    finished = pyqtSignal(list)                 # list[RenamePlan]

    def __init__(self, config: RenamerConfig, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.cfg = config
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Request cancellation. Honored at the next per-file boundary."""
        self._cancel.set()

    # ------------------------------------------------------------------
    def find_audio_files(self, directory: Path) -> List[Path]:
        """Return a sorted list of audio files in `directory`."""
        out: list[Path] = []
        for ext in self.cfg.extensions:
            out.extend(directory.glob(f"*{ext}"))
            out.extend(directory.glob(f"*{ext.upper()}"))
        return sorted(set(out))

    # ------------------------------------------------------------------
    def _transcribe_clip(self, clip_path: Path) -> str:
        """Run Buzz's WhisperFileTranscriber on a single trimmed clip.

        Returns the concatenated text of all returned segments.

        We construct a synthetic FileTranscriptionTask, run the transcriber
        synchronously, and pull text out of the resulting segments. This is
        the same machinery the rest of the app uses, just with no GUI in the
        loop.
        """
        file_options = FileTranscriptionOptions(
            file_paths=[str(clip_path)],
            output_formats=set(),  # we don't want any sidecar files written
        )
        task = FileTranscriptionTask(
            file_path=str(clip_path),
            transcription_options=self.cfg.transcription_options,
            file_transcription_options=file_options,
            model_path=self.cfg.model_path,
            source=FileTranscriptionTask.Source.FILE_IMPORT,
        )
        transcriber = WhisperFileTranscriber(task)

        # WhisperFileTranscriber.transcribe() is synchronous and returns a
        # List[Segment]. It uses multiprocessing internally to isolate the
        # heavy whisper code, so it's safe to call from the GUI thread, but we
        # still run it from a worker thread (see BulkRenamerThread below).
        segments: List[Segment] = transcriber.transcribe()
        return " ".join(s.text.strip() for s in segments).strip()

    # ------------------------------------------------------------------
    def _process_one(self, path: Path, tmp_dir: Path) -> RenamePlan:
        """Trim → transcribe → sanitize → produce a RenamePlan."""
        plan = RenamePlan(original_path=path)
        t0 = time.monotonic()
        try:
            clip = trim_to_temp_wav(path, self.cfg.trim_seconds, tmp_dir)
        except TrimError as e:
            plan.status = "error"
            plan.error = f"trim: {e}"
            plan.duration_sec = time.monotonic() - t0
            return plan

        try:
            text = self._transcribe_clip(clip)
        except Exception as e:  # noqa: BLE001 — transcribers raise many shapes
            logging.exception("Bulk renamer: transcription failed for %s", path.name)
            plan.status = "error"
            plan.error = f"transcribe: {e}"
            plan.duration_sec = time.monotonic() - t0
            return plan
        finally:
            try:
                clip.unlink()
            except OSError:
                pass

        plan.duration_sec = time.monotonic() - t0
        if not text:
            plan.status = "error"
            plan.error = "empty transcription"
            return plan

        plan.transcript = text
        snippet = first_n_words(text, self.cfg.first_words)
        stem = sanitize_filename(snippet, self.cfg.max_filename_len)
        if not stem:
            plan.status = "error"
            plan.error = "empty transcription after sanitize"
            return plan

        if self.cfg.keep_numeric_prefix:
            m = re.match(r'^(\d+[_\-])', path.stem)
            if m:
                stem = f"{m.group(1)}{stem}"

        plan.proposed_name = stem
        plan.proposed_path = path.with_name(stem + path.suffix)
        plan.status = "ready"
        return plan

    # ------------------------------------------------------------------
    def plan_renames(self, directory: Path) -> List[RenamePlan]:
        """Build a list of RenamePlans for all audio files in `directory`.

        Sequential. Emits ``progress`` after each file. Honors cancellation
        between files. Returns the full list (including any error/skipped
        plans). Does NOT commit any changes.
        """
        self._cancel.clear()
        files = self.find_audio_files(directory)
        if not files:
            self.log.emit(f"No audio files found in {directory}", "warn")
            self.finished.emit([])
            return []

        self.log.emit(f"Found {len(files)} audio file(s).", "info")

        plans: list[RenamePlan] = []
        with tempfile.TemporaryDirectory(prefix="buzz_rename_") as td:
            tmp_dir = Path(td)
            for i, path in enumerate(files, start=1):
                if self._cancel.is_set():
                    self.log.emit("Cancelled.", "warn")
                    # Mark the rest as skipped so callers see them
                    for remaining in files[i - 1:]:
                        plans.append(RenamePlan(
                            original_path=remaining,
                            status="skipped",
                            error="cancelled",
                        ))
                    break

                plan = self._process_one(path, tmp_dir)
                plans.append(plan)
                self.progress.emit(i, len(files), plan)

                if plan.status == "ready":
                    self.log.emit(
                        f"  {path.name} → {plan.proposed_name}{path.suffix}",
                        "info",
                    )
                else:
                    self.log.emit(f"  {path.name}: {plan.error}", "error")

        self._resolve_collisions(plans)
        self.finished.emit(plans)
        return plans

    # ------------------------------------------------------------------
    def _resolve_collisions(self, plans: List[RenamePlan]) -> None:
        """Resolve target-name collisions across the whole planned batch.

        Two kinds of conflict:
            (a) two plans propose the same target name;
            (b) a plan proposes a name that already exists on disk and is not
                itself one of the files being renamed.

        Strategy is configured via ``collision_strategy``: ``'suffix'`` (the
        default) appends ``_1``, ``_2``... ; ``'skip'`` marks the colliding
        plan as skipped.
        """
        plan_originals = {p.original_path for p in plans}
        targets_seen: set[Path] = set()

        if plans:
            dir_ = plans[0].original_path.parent
            on_disk_other = {p for p in dir_.iterdir()
                             if p.is_file() and p not in plan_originals}
        else:
            on_disk_other = set()

        for plan in plans:
            if plan.status != "ready":
                continue
            target = plan.proposed_path
            if target == plan.original_path:
                # No-op rename. Reserve the path so a *different* plan
                # doesn't try to rename to the same name.
                targets_seen.add(target)
                continue

            candidate = target
            n = 1
            while candidate in targets_seen or candidate in on_disk_other:
                if self.cfg.collision_strategy == "skip":
                    plan.status = "skipped"
                    plan.error = f"collision with {candidate.name}"
                    candidate = None
                    break
                stem = target.stem + f"_{n}"
                candidate = target.with_name(stem + target.suffix)
                n += 1
                if n > 999:
                    plan.status = "error"
                    plan.error = "too many collisions"
                    candidate = None
                    break
            if candidate is not None:
                plan.proposed_path = candidate
                targets_seen.add(candidate)


# ---------------------------------------------------------------------------
# Apply / undo (synchronous, not signal-driven)
# ---------------------------------------------------------------------------

def apply_plan(plans: List[RenamePlan],
               log_path: Optional[Path] = None) -> dict:
    """Execute the rename plan. Returns a summary dict.

    If ``log_path`` is given, writes a JSON undo log there containing every
    successfully-applied rename. Use ``undo_from_log`` to reverse.
    """
    applied: list[RenamePlan] = []
    skipped: list[RenamePlan] = []
    errors: list[RenamePlan] = []
    for plan in plans:
        if plan.status != "ready" or not plan.will_change:
            skipped.append(plan)
            continue
        try:
            plan.original_path.rename(plan.proposed_path)
            plan.status = "applied"
            applied.append(plan)
        except OSError as e:
            plan.status = "error"
            plan.error = f"rename failed: {e}"
            errors.append(plan)

    if log_path is not None and applied:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_data = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "renames": [
                {
                    "from": str(p.proposed_path),  # current location on disk
                    "to": str(p.original_path),    # original to restore on undo
                    "transcript": p.transcript,
                }
                for p in applied
            ],
        }
        log_path.write_text(json.dumps(log_data, indent=2))

    return {
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
    }


def undo_from_log(log_path: Path) -> dict:
    """Reverse a previously-applied batch using the JSON log."""
    data = json.loads(log_path.read_text())
    reverted: list = []
    failed: list = []
    for entry in data["renames"]:
        src = Path(entry["from"])
        dst = Path(entry["to"])
        if not src.exists():
            failed.append((entry, "source no longer exists"))
            continue
        if dst.exists():
            failed.append((entry, f"destination exists: {dst.name}"))
            continue
        try:
            src.rename(dst)
            reverted.append(entry)
        except OSError as e:
            failed.append((entry, str(e)))
    return {
        "reverted_count": len(reverted),
        "failed_count": len(failed),
        "reverted": reverted,
        "failed": failed,
    }
