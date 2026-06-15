"""
Shared helpers for installing Python packages at runtime via pip.

This module centralises the logic needed to run ``pip`` reliably across the
environments Buzz ships in: PyInstaller frozen bundles, Snap/Flatpak sandboxes,
uv/virtualenv installs and plain system Python. It is used by the plugin system
to install plugin-declared dependencies, and is intended to be the single source
of truth for runtime pip handling (the CUDA installer on the ``unbundle-cuda``
branch contains the original copy of this logic and should be unified with this
module when that branch merges).
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


def is_snap() -> bool:
    """Returns True if running inside a Snap package."""
    return "SNAP" in os.environ


def is_flatpak() -> bool:
    """Returns True if running inside a Flatpak sandbox."""
    return "FLATPAK_ID" in os.environ


def _in_virtualenv() -> bool:
    """Returns True if running inside a virtualenv or uv venv."""
    return sys.prefix != sys.base_prefix or "VIRTUAL_ENV" in os.environ


def subprocess_hide_window_kwargs() -> dict[str, Any]:
    """Return kwargs to hide the console window on Windows."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def get_pip_cmd() -> List[str]:
    """Return a ``[python, '-m', 'pip']`` command that is guaranteed to work.

    Handles three environments:
    - PyInstaller frozen bundle: ``sys.executable`` is the app binary and cannot
      run ``-m pip``. Use the bundled Python interpreter shipped alongside the
      app (``_MEIPASS/python/python(.exe)``), falling back to a real interpreter
      found on PATH.
    - Normal Python without pip (uv venv, minimal sandbox image): bootstrap pip
      via ``ensurepip``, then retry.
    - Normal Python with pip: use ``sys.executable`` directly.

    Raises:
        RuntimeError: if no usable Python interpreter / pip could be found.
    """
    import shutil

    # Frozen PyInstaller bundle — sys.executable can't run -m pip.
    if getattr(sys, "frozen", False):
        internal_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        python_name = "python.exe" if sys.platform == "win32" else "python3"
        bundled_python = internal_dir / "python" / python_name
        if bundled_python.is_file():
            return [str(bundled_python), "-m", "pip"]
        for candidate in ("python3.12", "python3", "python"):
            python = shutil.which(candidate)
            if python:
                return [python, "-m", "pip"]
        raise RuntimeError(
            "Could not find a Python interpreter. "
            "Please install Python 3.12 and try again."
        )

    pip_cmd = [sys.executable, "-m", "pip"]
    hide_kwargs = subprocess_hide_window_kwargs()

    # Check if pip is already available
    try:
        probe = subprocess.run(
            pip_cmd + ["--version"], capture_output=True, timeout=15, **hide_kwargs
        )
        if probe.returncode == 0:
            return pip_cmd
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.info("pip probe failed: %s", exc)

    # Try to bootstrap pip via ensurepip (available in CPython stdlib)
    logger.info("pip not found, bootstrapping via ensurepip...")
    bootstrap = subprocess.run(
        [sys.executable, "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        timeout=60,
        **hide_kwargs,
    )
    if bootstrap.returncode != 0:
        raise RuntimeError(
            "pip is not available and ensurepip failed. "
            "Please install pip manually and try again."
        )

    return pip_cmd


def pip_install(
    packages: List[str],
    extra_args: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Install ``packages`` via pip, streaming output to ``progress_callback``.

    Raises:
        RuntimeError: if pip is unavailable or the install fails.
    """
    if not packages:
        return

    cmd = get_pip_cmd() + ["install", "--break-system-packages"] + list(packages)
    if extra_args:
        cmd += extra_args

    logger.info("Running pip install: %s", " ".join(cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **subprocess_hide_window_kwargs(),
    )
    for line in process.stdout:
        line = line.rstrip()
        if line:
            logger.debug("pip: %s", line)
            if progress_callback:
                progress_callback(line)

    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"pip install failed with exit code {process.returncode}")
