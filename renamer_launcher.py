"""
Thin launcher for renamer_server.

Electron calls this script (NOT ``-m buzz.transcriber.renamer_server``).

Why does this file exist?
~~~~~~~~~~~~~~~~~~~~~~~~~
``WhisperFileTranscriber.transcribe()`` uses ``multiprocessing.Process``
with the *spawn* start-method on Windows.  ``spawn`` re-imports the
``__main__`` module in the child process.

If ``__main__`` is ``buzz.transcriber.renamer_server`` (which is what
``python -m …`` sets), the child re-imports websockets, model_loader,
PyQt6, bulk_renamer, torch, faster-whisper, etc. — a massive import
graph that causes native crashes (STATUS_ACCESS_VIOLATION 0xC0000005).

This launcher is intentionally *empty* at module level so that the
child process reimports nothing heavyweight.  The child only needs
to import ``whisper_file_transcriber`` (for the pickled target
function), which is handled by multiprocessing automatically.
"""

import multiprocessing
import sys


def _run_server():
    """Import the heavy server code and start the event loop."""
    import asyncio
    from buzz.transcriber.renamer_server import _main
    asyncio.run(_main())


if __name__ == "__main__":
    multiprocessing.freeze_support()

    # Only start the server in the *main* process.
    # multiprocessing children will reimport this file as __main__
    # (via _fixup_main_from_path) but must NOT re-run the server.
    if multiprocessing.parent_process() is None:
        _run_server()
