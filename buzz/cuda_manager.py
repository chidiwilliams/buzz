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

# NVIDIA runtime libraries — sourced from the official NVIDIA PyPI index.
# Versions are pinned to those resolved in uv.lock to prevent accidental upgrades.
# Packages that have wheels for both Linux and Windows (verified via uv.lock).
CUDA_NVIDIA_PACKAGES_COMMON = [
    "nvidia-cublas-cu12==12.9.1.4",
    "nvidia-cudnn-cu12==9.10.2.21",
]

# Packages that only have Linux (manylinux) wheels in uv.lock.
CUDA_NVIDIA_PACKAGES_LINUX = [
    "nvidia-cuda-cupti-cu12==12.9.79",
    "nvidia-cuda-nvrtc-cu12==12.9.86",
    "nvidia-cuda-runtime-cu12==12.9.79",
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


# The name of Buzz's own snap, as declared in snap/snapcraft.yaml.
SNAP_NAME = "buzz"


def is_snap() -> bool:
    """Returns True if running inside Buzz's own Snap package.

    Testing for SNAP alone is not enough: any snap-packaged tool that launches
    Buzz (e.g. a snap-installed uv used during development) exports SNAP* into
    the environment, which would send this multi-gigabyte CUDA install into an
    unrelated snap's user data.
    """
    return os.environ.get("SNAP_NAME") == SNAP_NAME


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


def _get_target_dir() -> Path | None:
    """Return the explicit --target directory for CUDA packages, or None.

    Snap and Flatpak get a dedicated writable directory; everything else
    installs into the venv or user site-packages and has no target dir.
    """
    if is_snap():
        snap_user_data = os.environ.get("SNAP_USER_DATA")
        if snap_user_data:
            return Path(snap_user_data) / "cuda_packages"
        return Path.home() / ".local" / "share" / "buzz" / "cuda_packages"
    if is_flatpak():
        xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(xdg_data) / "buzz" / "cuda_packages"
    return None


def _get_install_target() -> list[str]:
    """Return pip target flags for the current environment.

    In Snap/Flatpak the Python interpreter's user-site is disabled or points to
    the read-only bundle, so we use --target with an explicit writable path.
    In a virtualenv --user is forbidden; packages go into the venv directly.
    Otherwise we use --user so packages land in ~/.local.
    """
    target = _get_target_dir()
    if target is not None:
        target.mkdir(parents=True, exist_ok=True)
        return ["--target", str(target)]
    if _in_virtualenv():
        return []
    return ["--user"]


def _find_stale_cuda_dirs(target: Path) -> list[Path]:
    """Return existing cuda_packages dirs that a fresh install should replace.

    Includes the current target (a previous or half-finished install) and, under
    Snap, the same directory in other revisions: snapd copies $SNAP_USER_DATA
    forward on every refresh, so each revision keeps its own multi-gigabyte
    copy, and one built for an older Python is unusable after an upgrade.
    """
    stale: list[Path] = []
    if target.is_dir():
        stale.append(target)

    if is_snap():
        snap_user_data = os.environ.get("SNAP_USER_DATA")
        if snap_user_data:
            revisions_root = Path(snap_user_data).parent
            try:
                revisions = sorted(revisions_root.iterdir())
            except OSError as exc:
                logger.warning("Could not list snap revisions in %s: %s", revisions_root, exc)
                revisions = []
            for revision in revisions:
                # 'current' is a symlink to the active revision — skip it so we
                # never delete the same directory twice via two names.
                if revision.is_symlink() or not revision.is_dir():
                    continue
                candidate = revision / "cuda_packages"
                if candidate != target and candidate.is_dir():
                    stale.append(candidate)

    return stale


def _cleanup_old_cuda_packages(target: Path, report=None) -> None:
    """Delete previously installed CUDA packages before a fresh install.

    Installing over an existing directory leaves files from the old install
    behind, which is how an ABI-incompatible torch survives a Python upgrade
    and shadows the bundled one (see buzz/cuda_setup.py).
    """
    import shutil

    for stale in _find_stale_cuda_dirs(target):
        message = f"Removing previous CUDA packages in {stale}..."
        logger.info(message)
        if report:
            report(message)
        try:
            shutil.rmtree(stale)
        except OSError as exc:
            # Not fatal: pip will overwrite what it can, and cuda_setup skips
            # the directory if what remains is incompatible.
            logger.warning("Could not remove %s: %s", stale, exc)
            if report:
                report(f"Warning: could not remove {stale}: {exc}")


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

    target_dir = _get_target_dir()
    if target_dir is not None:
        # Only safe where we own the whole directory. A --user or venv install
        # shares its site-packages with the rest of Buzz's dependencies.
        _cleanup_old_cuda_packages(target_dir, report)

    target_flags = _get_install_target()

    nvidia_packages = CUDA_NVIDIA_PACKAGES_COMMON + (
        CUDA_NVIDIA_PACKAGES_LINUX if sys.platform != "win32" else []
    )
    report("Installing NVIDIA CUDA libraries...")
    _pip_install(
        nvidia_packages,
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


def _ensure_pip(python: str) -> list[str]:
    """Return [python, '-m', 'pip'], bootstrapping pip via ensurepip if needed."""
    hide_kwargs = _subprocess_hide_window_kwargs()
    pip_cmd = [python, "-m", "pip"]
    probe = subprocess.run(pip_cmd + ["--version"], capture_output=True, timeout=15, **hide_kwargs)
    if probe.returncode == 0:
        return pip_cmd
    logger.info("pip not found for %s, bootstrapping via ensurepip...", python)
    bootstrap = subprocess.run(
        [python, "-m", "ensurepip", "--upgrade"],
        capture_output=True, timeout=60, **hide_kwargs,
    )
    if bootstrap.returncode != 0:
        raise RuntimeError(
            f"pip is not available for {python} and ensurepip failed. "
            "Please install pip manually and try again."
        )
    return pip_cmd


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
    # Use the bundled interpreter shipped alongside the app. Its version always
    # matches the one Buzz was frozen with, so derive it rather than hardcoding:
    # the CUDA wheels are ABI-specific and a mismatch installs unusable packages.
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if getattr(sys, "frozen", False):
        # PyInstaller extracts bundled data to sys._MEIPASS (_internal dir)
        internal_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        python_name = "python.exe" if sys.platform == "win32" else "python3"
        bundled_python = internal_dir / "python" / python_name
        if bundled_python.is_file():
            return _ensure_pip(str(bundled_python))
        # Fallback: look in PATH
        for candidate in (f"python{version}", "python3", "python"):
            python = shutil.which(candidate)
            if python:
                return _ensure_pip(python)
        raise RuntimeError(
            "Could not find a Python interpreter. "
            f"Please install Python {version} and try again."
        )

    return _ensure_pip(sys.executable)


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
