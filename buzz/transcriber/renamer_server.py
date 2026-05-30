"""
buzz/transcriber/renamer_server.py

asyncio WebSocket server that exposes BulkRenamer to the Electron UI.

Usage (from project root, inside the venv):
    python -m buzz.transcriber.renamer_server

On startup the server prints a single line to stdout:
    PORT:<n>
so the Electron main process knows which port to connect to.

Only one WebSocket client is accepted at a time (the Electron renderer).

Protocol
--------
Client -> Server (JSON):
  {"cmd": "start_preview",    "directory": "...", "config": {...}}
  {"cmd": "cancel"}
  {"cmd": "apply_renames",    "folder": "...", "plans": [...]}
  {"cmd": "undo",             "folder": "..."}
  {"cmd": "list_models"}
  {"cmd": "download_model",   "model_type": "...", "model_size": "...",
                               "hugging_face_model_id": ""}
  {"cmd": "cancel_download"}

Server -> Client (JSON):
  {"event": "ready"}
  {"event": "log",              "message": "...", "level": "info|warn|error"}
  {"event": "progress",        "done": N, "total": N, "plan": {...}}
  {"event": "preview_done",    "plans": [...]}
  {"event": "apply_done",      "summary": {...}}
  {"event": "undo_done",       "result": {...}}
  {"event": "models",          "models": [...]}
  {"event": "download_progress","downloaded": N, "total": N, "percent": N}
  {"event": "download_done",   "model_path": "..."}
  {"event": "error",           "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import os
import socket
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# MUST be imported first — sets up CUDA/nvidia DLL paths before torch loads.
# Without this, ctranslate2 (faster-whisper) crashes in subprocesses with
# STATUS_ACCESS_VIOLATION (0xC0000005) on Windows.
# ---------------------------------------------------------------------------
import buzz.cuda_setup  # noqa: F401  # auto-runs setup_cuda_libraries()

from buzz.assets import APP_BASE_DIR  # noqa: E402
from platformdirs import user_cache_dir  # noqa: E402

# Route HuggingFace downloads to the same Buzz cache the GUI uses
_model_root = os.environ.get("BUZZ_MODEL_ROOT")
if _model_root:
    os.environ.setdefault("HF_HOME", os.path.dirname(_model_root))
else:
    os.environ.setdefault("HF_HOME", user_cache_dir("Buzz"))

# Add the buzz package dir to the Windows DLL search path so that
# ctranslate2, faster-whisper, whisper.cpp etc. can find their native libs.
if sys.platform == "win32":
    os.add_dll_directory(APP_BASE_DIR)
    for _sub in ("dll_backup", os.path.join("onnxruntime", "capi")):
        _d = os.path.join(APP_BASE_DIR, _sub)
        if os.path.isdir(_d):
            os.add_dll_directory(_d)

# Add APP_BASE_DIR to PATH so ffmpeg and other bundled binaries are found
# (mirrors what buzz.py does at startup).
os.environ["PATH"] = os.pathsep.join(
    [APP_BASE_DIR, os.path.join(APP_BASE_DIR, "_internal")]
    + [os.environ.get("PATH", "")]
)

# ---------------------------------------------------------------------------
# A headless QCoreApplication is required before importing any Qt class.
# WhisperFileTranscriber inherits QObject but its transcribe() method is
# entirely synchronous / multiprocessing-based — no Qt event loop needed.
#
# CRITICAL: Only create the QCoreApplication in the **main** server process.
# On Windows with multiprocessing 'spawn', child processes re-import this
# module. Creating a QCoreApplication (especially with QT_QPA_PLATFORM=
# offscreen) inside the child causes the transcription subprocess to crash
# with STATUS_ACCESS_VIOLATION (0xC0000005).
# ---------------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication  # noqa: E402

if multiprocessing.parent_process() is None:
    # Main server process — create the Qt app that BulkRenamer (QObject) needs
    _qt_app: QCoreApplication = (
        QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    )  # type: ignore[assignment]

try:
    import websockets  # noqa: E402
    import websockets.exceptions  # noqa: E402
except ImportError:
    print(
        "ERROR: 'websockets' is not installed.\n"
        "Run:  pip install websockets",
        file=sys.stderr,
    )
    sys.exit(1)

from buzz.model_loader import (  # noqa: E402
    ModelDownloader,
    ModelType,
    TranscriptionModel,
    WhisperModelSize,
)
from buzz.transcriber.bulk_renamer import (  # noqa: E402
    BulkRenamer,
    RenamePlan,
    RenamerConfig,
    apply_plan,
    undo_from_log,
)
from buzz.transcriber.transcriber import LANGUAGES, Task, TranscriptionOptions  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(levelname)s %(name)s: %(message)s")


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _plan_to_dict(plan: RenamePlan) -> Dict[str, Any]:
    return {
        "original_path": str(plan.original_path),
        "transcript": plan.transcript,
        "proposed_name": plan.proposed_name,
        "proposed_path": str(plan.proposed_path) if plan.proposed_path else None,
        "status": plan.status,
        "error": plan.error,
        "duration_sec": round(plan.duration_sec, 2),
        "will_change": plan.will_change,
    }


def _plan_from_dict(d: Dict[str, Any]) -> RenamePlan:
    p = RenamePlan(original_path=Path(d["original_path"]))
    p.transcript = d.get("transcript", "")
    p.proposed_name = d.get("proposed_name", "")
    raw_pp = d.get("proposed_path")
    p.proposed_path = Path(raw_pp) if raw_pp else None
    p.status = d.get("status", "pending")
    p.error = d.get("error", "")
    p.duration_sec = float(d.get("duration_sec", 0.0))
    return p


def _build_config(raw: Dict[str, Any]) -> RenamerConfig:
    """Build a RenamerConfig from the JSON config block sent by the UI."""
    model_type_str = raw.get("model_type", ModelType.WHISPER_CPP.value)
    try:
        model_type = ModelType(model_type_str)
    except ValueError:
        model_type = ModelType.WHISPER_CPP

    size_str = raw.get("model_size", WhisperModelSize.BASE.value)
    try:
        size = WhisperModelSize(size_str)
    except ValueError:
        size = WhisperModelSize.BASE

    hf_id = raw.get("hugging_face_model_id", "")
    model = TranscriptionModel(
        model_type=model_type,
        whisper_model_size=size,
        hugging_face_model_id=hf_id,
    )

    language = raw.get("language") or None
    opts = TranscriptionOptions(
        language=language,
        task=Task.TRANSCRIBE,
        model=model,
        word_level_timings=False,
        extract_speech=False,
        initial_prompt=raw.get("initial_prompt", ""),
    )

    # model_path: explicit path provided by the UI (required for whisper.cpp,
    # optional for other backends — they resolve it via get_local_model_path()).
    model_path = raw.get("model_path", "")
    if not model_path:
        model_path = model.get_local_model_path() or ""

    return RenamerConfig(
        transcription_options=opts,
        model_path=model_path,
        trim_seconds=float(raw.get("trim_seconds", 5.0)),
        first_words=int(raw.get("first_words", 6)),
        max_filename_len=int(raw.get("max_filename_len", 50)),
        keep_numeric_prefix=bool(raw.get("keep_numeric_prefix", False)),
        collision_strategy=raw.get("collision_strategy", "suffix"),
    )


# ---------------------------------------------------------------------------
# Session: one per connected Electron client
# ---------------------------------------------------------------------------

class _Session:
    """Manages a single connected WebSocket client."""

    def __init__(self, ws) -> None:
        self._ws = ws
        self._loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._cancel_event = threading.Event()

    # ---- thread-safe helpers ------------------------------------------------

    async def _send(self, event: Dict[str, Any]) -> None:
        try:
            await self._ws.send(json.dumps(event))
        except websockets.exceptions.ConnectionClosed:
            pass

    def _post(self, event: Dict[str, Any]) -> None:
        """Safe to call from worker threads."""
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    async def _drain_until(self, stop_event: str) -> None:
        """Forward queued events to the WebSocket until `stop_event` arrives."""
        while True:
            ev = await self._queue.get()
            await self._send(ev)
            if ev.get("event") == stop_event:
                break

    # ---- command handlers ---------------------------------------------------

    async def _cmd_list_models(self, _msg: Dict) -> None:
        models = []
        for mt in ModelType:
            if not mt.is_available():
                continue
            sizes = []
            if mt in (ModelType.WHISPER, ModelType.WHISPER_CPP,
                      ModelType.FASTER_WHISPER):
                for sz in WhisperModelSize:
                    try:
                        local = TranscriptionModel(
                            model_type=mt, whisper_model_size=sz
                        ).get_local_model_path()
                    except (KeyError, Exception):
                        # Some WhisperModelSize values (e.g. 'lumii') are
                        # Buzz-specific and not in openai-whisper's _MODELS.
                        local = None
                    sizes.append({
                        "size": sz.value,
                        "label": str(sz),
                        "downloaded": local is not None,
                    })
            models.append({
                "type": mt.value,
                "sizes": sizes,
                "needs_path": mt == ModelType.WHISPER_CPP,
            })
        await self._send({"event": "models", "models": models})

    async def _cmd_list_languages(self, _msg: Dict) -> None:
        """Return all Whisper-supported languages sorted alphabetically by name."""
        langs = sorted(
            [{"code": code, "name": name} for code, name in LANGUAGES.items()],
            key=lambda x: x["name"].lower(),
        )
        await self._send({"event": "languages", "languages": langs})

    async def _cmd_list_files(self, msg: Dict) -> None:
        """Return the list of audio files in a folder (no transcription)."""
        directory = Path(msg.get("directory", ""))
        if not directory.is_dir():
            await self._send({"event": "error",
                               "message": f"Not a directory: {directory}"})
            return
        # Scan directly — do NOT instantiate BulkRenamer (a QObject) here.
        # Creating a QObject outside the Qt event loop can cause instability.
        AUDIO_EXTENSIONS = (
            ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".opus",
        )
        found: List[Path] = []
        for ext in AUDIO_EXTENSIONS:
            found.extend(directory.glob(f"*{ext}"))
            found.extend(directory.glob(f"*{ext.upper()}"))
        files = sorted(set(found))
        await self._send({
            "event": "files_listed",
            "files": [str(f) for f in files],
        })

    async def _cmd_start_preview(self, msg: Dict) -> None:
        directory = Path(msg["directory"])
        if not directory.is_dir():
            await self._send({"event": "error",
                               "message": f"Not a directory: {directory}"})
            return

        try:
            cfg = _build_config(msg.get("config", {}))
        except Exception as exc:
            await self._send({"event": "error",
                               "message": f"Config error: {exc}"})
            return

        if not cfg.model_path:
            await self._send({
                "event": "error",
                "message": (
                    "No model found locally. "
                    "Please download a model first or provide a model file path."
                ),
            })
            return

        self._cancel_event.clear()
        renamer = BulkRenamer(cfg)
        files = renamer.find_audio_files(directory)
        total = len(files)

        if total == 0:
            await self._send({"event": "log",
                               "message": "No audio files found in that folder.",
                               "level": "warn"})
            await self._send({"event": "preview_done", "plans": []})
            return

        await self._send({"event": "log",
                           "message": f"Found {total} audio file(s).",
                           "level": "info"})

        plans: List[RenamePlan] = []

        def _worker() -> None:
            with tempfile.TemporaryDirectory(prefix="buzz_rename_") as td:
                tmp_dir = Path(td)
                for i, path in enumerate(files, start=1):
                    if self._cancel_event.is_set():
                        self._post({"event": "log",
                                    "message": "Cancelled by user.",
                                    "level": "warn"})
                        # Fill remaining as skipped
                        for remaining in files[i - 1:]:
                            plans.append(RenamePlan(
                                original_path=remaining,
                                status="skipped",
                                error="cancelled",
                            ))
                        break

                    plan = renamer._process_one(path, tmp_dir)
                    plans.append(plan)
                    self._post({
                        "event": "progress",
                        "done": i,
                        "total": total,
                        "plan": _plan_to_dict(plan),
                    })
                    level = "info" if plan.status == "ready" else "error"
                    if plan.status == "ready":
                        msg_text = (
                            f"  {path.name} → "
                            f"{plan.proposed_name}{path.suffix}"
                        )
                    else:
                        msg_text = f"  {path.name}: {plan.error}"
                    self._post({"event": "log",
                                "message": msg_text,
                                "level": level})

            # Resolve cross-batch collisions
            renamer._resolve_collisions(plans)
            self._post({
                "event": "preview_done",
                "plans": [_plan_to_dict(p) for p in plans],
            })

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        await self._drain_until("preview_done")

    async def _cmd_cancel(self, _msg: Dict) -> None:
        self._cancel_event.set()
        await self._send({"event": "log",
                           "message": "Cancellation requested.",
                           "level": "warn"})

    async def _cmd_apply_renames(self, msg: Dict) -> None:
        raw_plans = msg.get("plans", [])
        plans = [_plan_from_dict(d) for d in raw_plans]
        if not plans:
            await self._send({"event": "error",
                               "message": "No plans provided."})
            return

        folder_str = msg.get("folder")
        folder = (
            Path(folder_str)
            if folder_str
            else plans[0].original_path.parent
        )
        log_path = (
            folder / f".undo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        try:
            summary = apply_plan(plans, log_path)
        except Exception as exc:
            await self._send({"event": "error",
                               "message": f"Apply failed: {exc}"})
            return

        await self._send({
            "event": "apply_done",
            "summary": {
                "applied_count": summary["applied_count"],
                "skipped_count": summary["skipped_count"],
                "error_count": summary["error_count"],
            },
        })

    async def _cmd_undo(self, msg: Dict) -> None:
        folder = Path(msg.get("folder", "."))
        logs = sorted(folder.glob(".undo_*.json"), reverse=True)
        if not logs:
            await self._send({"event": "error",
                               "message": "No undo log found in this folder."})
            return
        try:
            result = undo_from_log(logs[0])
        except Exception as exc:
            await self._send({"event": "error",
                               "message": f"Undo failed: {exc}"})
            return

        await self._send({
            "event": "undo_done",
            "result": {
                "reverted_count": result["reverted_count"],
                "failed_count": result["failed_count"],
                "log_name": logs[0].name,
            },
        })

    # ---- download handlers --------------------------------------------------

    async def _cmd_download_model(self, msg: Dict) -> None:
        """Download a model using Buzz's ModelLoader, streaming progress."""
        model_type_str = msg.get("model_type", ModelType.WHISPER_CPP.value)
        model_size_str = msg.get("model_size", WhisperModelSize.BASE.value)
        hf_id = msg.get("hugging_face_model_id", "")

        try:
            model_type = ModelType(model_type_str)
        except ValueError:
            await self._send({"event": "error",
                               "message": f"Unknown model type: {model_type_str}"})
            return

        try:
            size = WhisperModelSize(model_size_str)
        except ValueError:
            size = WhisperModelSize.BASE

        model = TranscriptionModel(
            model_type=model_type,
            whisper_model_size=size,
            hugging_face_model_id=hf_id,
        )

        loop = asyncio.get_event_loop()
        done_event = asyncio.Event()
        result: Dict = {}

        def _on_progress(progress):
            # progress is a tuple (downloaded_bytes, total_bytes)
            downloaded, total = progress
            pct = round(downloaded / total * 100, 1) if total else 0
            loop.call_soon_threadsafe(
                self._queue.put_nowait,
                {"event": "download_progress",
                 "downloaded": downloaded,
                 "total": total,
                 "percent": pct},
            )

        def _on_finished(path: str):
            result["path"] = path
            loop.call_soon_threadsafe(
                self._queue.put_nowait,
                {"event": "download_done", "model_path": path},
            )
            loop.call_soon_threadsafe(done_event.set)

        def _on_error(err: str):
            result["error"] = err
            loop.call_soon_threadsafe(
                self._queue.put_nowait,
                {"event": "error", "message": f"Download failed: {err}"},
            )
            loop.call_soon_threadsafe(done_event.set)

        loader = ModelDownloader(model=model)
        loader.signals.progress.connect(_on_progress)
        loader.signals.finished.connect(_on_finished)
        loader.signals.error.connect(_on_error)

        self._active_loader = loader

        await self._send({"event": "log",
                           "message": f"Starting download: {model_type_str} / {model_size_str}",
                           "level": "info"})

        thread = threading.Thread(target=loader.run, daemon=True)
        thread.start()

        # Drain progress/done events until download completes.
        # HuggingFace downloads (Faster Whisper, Whisper.cpp) run in a subprocess
        # and emit only one (0,100) progress signal — so we send periodic heartbeats
        # to keep the UI alive and informed.
        import time as _time
        last_heartbeat = _time.monotonic()
        heartbeat_interval = 5  # seconds
        elapsed_ticks = 0

        while not done_event.is_set():
            try:
                ev = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                await self._send(ev)
            except asyncio.TimeoutError:
                now = _time.monotonic()
                if now - last_heartbeat >= heartbeat_interval:
                    elapsed_ticks += heartbeat_interval
                    mins = elapsed_ticks // 60
                    secs = elapsed_ticks % 60
                    elapsed_str = f"{mins}m {secs}s" if mins else f"{secs}s"
                    await self._send({
                        "event": "download_progress",
                        "downloaded": 0,
                        "total": 0,   # 0/0 signals indeterminate to the UI
                        "percent": -1,
                        "elapsed": elapsed_str,
                    })
                    last_heartbeat = now
                continue

        self._active_loader = None

    async def _cmd_cancel_download(self, _msg: Dict) -> None:
        loader = getattr(self, "_active_loader", None)
        if loader is not None:
            loader.stopped = True
            await self._send({"event": "log",
                               "message": "Download cancelled.",
                               "level": "warn"})
        else:
            await self._send({"event": "log",
                               "message": "No active download to cancel.",
                               "level": "warn"})

    # ---- main loop ----------------------------------------------------------

    async def run(self) -> None:
        self._active_loader = None
        await self._send({"event": "ready"})
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            cmd = msg.get("cmd")
            log.debug("Received command: %s", cmd)

            if cmd == "list_models":
                await self._cmd_list_models(msg)
            elif cmd == "list_files":
                await self._cmd_list_files(msg)
            elif cmd == "start_preview":
                await self._cmd_start_preview(msg)
            elif cmd == "cancel":
                await self._cmd_cancel(msg)
            elif cmd == "apply_renames":
                await self._cmd_apply_renames(msg)
            elif cmd == "undo":
                await self._cmd_undo(msg)
            elif cmd == "download_model":
                await self._cmd_download_model(msg)
            elif cmd == "cancel_download":
                await self._cmd_cancel_download(msg)
            elif cmd == "list_languages":
                await self._cmd_list_languages(msg)
            else:
                log.warning("Unknown command: %s", cmd)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    # Pick a free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    async def _handler(ws):
        session = _Session(ws)
        try:
            await session.run()
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            log.exception("Unhandled error in session")

    async with websockets.serve(_handler, "127.0.0.1", port):
        # Tell the parent process (Electron main.js) which port we chose
        print(f"PORT:{port}", flush=True)
        log.info("Renamer server ready on ws://127.0.0.1:%d", port)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    # Required on Windows: prevents multiprocessing subprocesses from
    # re-running this startup code when they re-import the main module.
    multiprocessing.freeze_support()
    asyncio.run(_main())
