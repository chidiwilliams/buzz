"""
Utilities for checking and installing CUDA support at runtime.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Pinned versions matching uv.lock for the cu129 build of PyTorch.
# All packages are served from the PyTorch wheel index; pip selects the
# correct platform wheel automatically (Linux-only packages have no
# Windows wheel and are silently skipped by pip on Windows).
CUDA_INDEX_URL = "https://download.pytorch.org/whl/cu129"
CUDA_TORCH_PACKAGES = [
    "torch==2.8.0+cu129",
    "torchaudio==2.8.0+cu129",
]
# Full set of NVIDIA runtime libraries required by torch+cu129.
# Versions are pinned to those resolved in uv.lock to prevent accidental upgrades.
CUDA_NVIDIA_PACKAGES = [
    "nvidia-cublas-cu12==12.9.1.4",
    "nvidia-cuda-cupti-cu12==12.9.79",
    "nvidia-cuda-nvrtc-cu12==12.9.86",
    "nvidia-cuda-runtime-cu12==12.9.79",
    "nvidia-cudnn-cu12==9.10.2.21",
    "nvidia-cufft-cu12==11.4.1.4",
    "nvidia-cufile-cu12==1.14.1.1",
    "nvidia-curand-cu12==10.3.10.19",
    "nvidia-cusolver-cu12==11.7.5.82",
    "nvidia-cusparse-cu12==12.5.10.65",
    "nvidia-cusparselt-cu12==0.7.1",
    "nvidia-nccl-cu12==2.27.3",
    "nvidia-nvjitlink-cu12==12.9.86",
    "nvidia-nvtx-cu12==12.9.79",
]


def is_snap() -> bool:
    """Returns True if running inside a Snap package."""
    return "SNAP" in os.environ


def is_flatpak() -> bool:
    """Returns True if running inside a Flatpak sandbox."""
    return "FLATPAK_ID" in os.environ


def should_offer_cuda_prompt() -> bool:
    """Returns True on platforms where in-app CUDA installation is supported."""
    if sys.platform == "win32":
        return True
    if sys.platform == "linux":
        return is_snap() or is_flatpak()
    return False


def is_cuda_torch_installed() -> bool:
    """Returns True if torch with CUDA support is available."""
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        logger.info(
            "CUDA check: torch version=%s, cuda_built=%s, cuda_available=%s, cuda_version=%s",
            torch.__version__,
            torch.version.cuda,
            cuda_available,
            torch.version.cuda if cuda_available else "N/A",
        )
        if not cuda_available and torch.version.cuda:
            # CUDA was compiled in but is not available at runtime — likely a DLL loading issue
            logger.warning(
                "CUDA check: torch was built with CUDA %s but cuda is not available. "
                "This usually means CUDA DLLs failed to load. torch.cuda.is_available() returned False.",
                torch.version.cuda,
            )
        return cuda_available
    except ImportError:
        logger.info("CUDA check: torch is not installed")
        return False


def is_nvidia_gpu_present() -> bool:
    """Returns True if an NVIDIA GPU is detected.

    Tries nvidia-smi first, then falls back to /proc/driver/nvidia/version
    which is accessible inside Snap and Flatpak sandboxes without executing
    an external binary.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
            **_subprocess_hide_window_kwargs(),
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: kernel driver version file — present when NVIDIA driver is loaded
    return Path("/proc/driver/nvidia/version").exists()


def _in_virtualenv() -> bool:
    """Returns True if running inside a virtualenv or uv venv."""
    return sys.prefix != sys.base_prefix or "VIRTUAL_ENV" in os.environ


def _get_install_target() -> list[str]:
    """Return pip target flags for the current environment.

    In Snap/Flatpak the Python interpreter's user-site is disabled or points to
    the read-only bundle, so we use --target with an explicit writable path.
    In a virtualenv --user is forbidden; packages go into the venv directly.
    Otherwise we use --user so packages land in ~/.local.
    """
    if is_snap():
        snap_user_data = os.environ.get("SNAP_USER_DATA")
        if snap_user_data:
            target = str(Path(snap_user_data) / "cuda_packages")
        else:
            target = str(Path.home() / ".local" / "share" / "buzz" / "cuda_packages")
        Path(target).mkdir(parents=True, exist_ok=True)
        return ["--target", target]
    if is_flatpak():
        xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        target = str(Path(xdg_data) / "buzz" / "cuda_packages")
        Path(target).mkdir(parents=True, exist_ok=True)
        return ["--target", target]
    if _in_virtualenv():
        return []
    return ["--user"]


def install_cuda(progress_callback=None):
    """
    Install CUDA-enabled torch and nvidia libraries.

    Args:
        progress_callback: Optional callable(str) called with status messages.
    """
    def report(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    target_flags = _get_install_target()

    report("Installing NVIDIA CUDA libraries...")
    _pip_install(
        CUDA_NVIDIA_PACKAGES,
        extra_args=["--index-url", CUDA_INDEX_URL] + target_flags,
        progress_callback=report,
    )

    report("Installing CUDA-enabled PyTorch...")
    _pip_install(
        CUDA_TORCH_PACKAGES,
        extra_args=["--index-url", CUDA_INDEX_URL, "--no-deps"] + target_flags,
        progress_callback=report,
    )

    report("CUDA installation complete. Please restart Buzz to enable GPU acceleration.")


def _get_pip_cmd() -> list[str]:
    """Return a [python, '-m', 'pip'] command that is guaranteed to work.

    Handles three environments:
    - PyInstaller frozen bundle: sys.executable is the app binary; find a real
      Python interpreter in PATH instead.
    - Normal Python without pip (uv venv, minimal snap/flatpak image): bootstrap
      pip via ensurepip, then retry.
    - Normal Python with pip: use sys.executable directly.
    """
    import shutil

    # Frozen PyInstaller bundle — sys.executable can't run -m pip.
    # Use the bundled Python 3.12 interpreter shipped alongside the app.
    if getattr(sys, "frozen", False):
        # PyInstaller extracts bundled data to sys._MEIPASS (_internal dir)
        internal_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        python_name = "python.exe" if sys.platform == "win32" else "python3"
        bundled_python = internal_dir / "python" / python_name
        if bundled_python.is_file():
            return [str(bundled_python), "-m", "pip"]
        # Fallback: look in PATH
        for candidate in ("python3.12", "python3", "python"):
            python = shutil.which(candidate)
            if python:
                return [python, "-m", "pip"]
        raise RuntimeError(
            "Could not find a Python interpreter. "
            "Please install Python 3.12 and try again."
        )

    pip_cmd = [sys.executable, "-m", "pip"]
    hide_kwargs = _subprocess_hide_window_kwargs()

    # Check if pip is already available
    probe = subprocess.run(pip_cmd + ["--version"], capture_output=True, timeout=15, **hide_kwargs)
    if probe.returncode == 0:
        return pip_cmd

    # Try to bootstrap pip via ensurepip (available in CPython stdlib)
    logger.info("pip not found, bootstrapping via ensurepip...")
    bootstrap = subprocess.run(
        [sys.executable, "-m", "ensurepip", "--upgrade"],
        capture_output=True, timeout=60, **hide_kwargs,
    )
    if bootstrap.returncode != 0:
        raise RuntimeError(
            "pip is not available and ensurepip failed. "
            "Please install pip manually and try again."
        )

    return pip_cmd


def _subprocess_hide_window_kwargs() -> dict[str, Any]:
    """Return kwargs to hide the console window on Windows."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _pip_install(packages, extra_args=None, progress_callback=None):
    cmd = _get_pip_cmd() + ["install", "--break-system-packages"] + packages
    if extra_args:
        cmd += extra_args

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **_subprocess_hide_window_kwargs(),
    )
    for line in process.stdout:
        line = line.rstrip()
        if line and progress_callback:
            progress_callback(line)

    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"pip install failed with exit code {process.returncode}")
