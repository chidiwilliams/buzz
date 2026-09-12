"""
Utilities for checking and installing CUDA support at runtime.
"""

import logging
import os
import shutil
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

# Name of the private virtual environment holding the CUDA packages.
CUDA_ENV_DIR_NAME = "cuda_env"

# Name used before the switch to a private venv. Still cleaned up so an
# upgrade does not leave several gigabytes of orphaned wheels behind.
LEGACY_CUDA_DIR_NAME = "cuda_packages"


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


def is_appimage() -> bool:
    """Returns True if this Buzz is running from its own AppImage.

    The type-2 runtime exports APPIMAGE (the .AppImage path) and APPDIR (the
    mounted bundle). Testing APPIMAGE alone is not enough, for the same reason
    as in is_snap(): any AppImage-packaged tool that launches Buzz leaks those
    into the environment. Requiring the running executable to live inside
    APPDIR ties the answer to *this* bundle.
    """
    appdir = os.environ.get("APPDIR")
    if not appdir or "APPIMAGE" not in os.environ:
        return False
    try:
        return Path(sys.executable).resolve().is_relative_to(Path(appdir).resolve())
    except OSError:
        return False


def should_offer_cuda_prompt() -> bool:
    """Returns True on platforms where in-app CUDA installation is supported."""
    
    return sys.platform in ("win32", "linux")


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


def get_cuda_root_dir() -> Path:
    """Return the writable Buzz-owned directory that holds the CUDA install.

    Snap and Flatpak have their own per-sandbox data directories. Everywhere
    else this is Buzz's platform data directory (on Windows a subdirectory of
    %LOCALAPPDATA%\\Buzz, which the uninstaller offers to delete), so the
    multi-gigabyte CUDA install never lands in a shared site-packages and goes
    away with the app.
    """
    if is_snap():
        snap_user_data = os.environ.get("SNAP_USER_DATA")
        if snap_user_data:
            return Path(snap_user_data)
        return Path.home() / ".local" / "share" / "buzz"
    if is_flatpak():
        xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(xdg_data) / "buzz"

    from platformdirs import user_data_dir

    return Path(user_data_dir("Buzz"))


def get_cuda_env_dir() -> Path:
    """Return the path of the private virtualenv holding the CUDA packages."""
    return get_cuda_root_dir() / CUDA_ENV_DIR_NAME


def get_cuda_env_site_packages(env_dir: Path | None = None) -> Path | None:
    """Return the site-packages directory inside the CUDA venv, if it exists.

    The Linux layout embeds the Python version (lib/python3.13/site-packages),
    so it is globbed rather than derived: after a Buzz upgrade to a different
    Python the directory is still found, and the ABI check in buzz/cuda_setup.py
    is what decides whether it may be used.
    """
    env_dir = env_dir if env_dir is not None else get_cuda_env_dir()

    if sys.platform == "win32":
        site_packages = env_dir / "Lib" / "site-packages"
        return site_packages if site_packages.is_dir() else None

    candidates = sorted(env_dir.glob("lib/python3.*/site-packages"))
    return candidates[-1] if candidates else None


def _find_stale_cuda_dirs(env_dir: Path) -> list[Path]:
    """Return existing CUDA install dirs that a fresh install should replace.

    Includes the current env (a previous or half-finished install), the legacy
    --target directory it replaced, and, under Snap, the same directories in
    other revisions: snapd copies $SNAP_USER_DATA forward on every refresh, so
    each revision keeps its own multi-gigabyte copy, and one built for an older
    Python is unusable after an upgrade.
    """
    roots = [env_dir.parent]

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
                if revision not in roots:
                    roots.append(revision)

    stale: list[Path] = []
    for root in roots:
        for name in (CUDA_ENV_DIR_NAME, LEGACY_CUDA_DIR_NAME):
            candidate = root / name
            if candidate.is_dir() and candidate not in stale:
                stale.append(candidate)
    return stale


def _cleanup_old_cuda_packages(env_dir: Path, report=None) -> None:
    """Delete previously installed CUDA packages before a fresh install.

    Installing over an existing environment leaves files from the old install
    behind, which is how an ABI-incompatible torch survives a Python upgrade
    and shadows the bundled one (see buzz/cuda_setup.py).
    """
    for stale in _find_stale_cuda_dirs(env_dir):
        message = f"Removing previous CUDA packages in {stale}..."
        logger.info(message)
        if report:
            report(message)
        try:
            shutil.rmtree(stale)
        except OSError as exc:
            # Not fatal: the install below recreates what it can, and cuda_setup
            # skips the directory if what remains is incompatible.
            logger.warning("Could not remove %s: %s", stale, exc)
            if report:
                report(f"Warning: could not remove {stale}: {exc}")


def install_cuda(progress_callback=None):
    """
    Install CUDA-enabled torch and nvidia libraries into a private venv.

    Nothing is written to the user's global or user site-packages: everything
    lands in get_cuda_env_dir(), which Buzz puts on sys.path at startup and
    removes when GPU support is reinstalled.

    Args:
        progress_callback: Optional callable(str) called with status messages.
    """
    def report(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    env_dir = get_cuda_env_dir()
    _cleanup_old_cuda_packages(env_dir, report)

    report(f"Creating environment for CUDA packages in {env_dir}...")
    install_cmd = _create_cuda_env(env_dir, progress_callback=report)

    nvidia_packages = CUDA_NVIDIA_PACKAGES_COMMON + (
        CUDA_NVIDIA_PACKAGES_LINUX if sys.platform != "win32" else []
    )
    report("Installing NVIDIA CUDA libraries...")
    _run_install(
        install_cmd,
        nvidia_packages,
        extra_args=["--index-url", CUDA_INDEX_URL],
        progress_callback=report,
    )

    report("Installing CUDA-enabled PyTorch...")
    _run_install(
        install_cmd,
        CUDA_TORCH_PACKAGES,
        extra_args=["--index-url", CUDA_INDEX_URL, "--no-deps"],
        progress_callback=report,
    )

    report("CUDA installation complete. Please restart Buzz to enable GPU acceleration.")


def get_python_version() -> str:
    """Return the major.minor version the CUDA wheels must be built for."""
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _interpreter_version_matches(python: str) -> bool:
    """Return True if `python` reports the same major.minor as the running one.

    The CUDA wheels are ABI-specific and Buzz imports them into its own
    process, so an interpreter of any other version is useless here — torch
    publishes no wheel for it (a newer Python), or the extension modules it
    does install cannot be loaded by the app.
    """
    try:
        probe = subprocess.run(
            [python, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=30,
            **_subprocess_hide_window_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not probe the version of %s: %s", python, exc)
        return False

    if probe.returncode != 0:
        return False
    return probe.stdout.strip() == get_python_version()


def _get_base_python() -> str | None:
    """Return a real Python interpreter that can create the CUDA venv.

    In a frozen PyInstaller bundle sys.executable is the app binary and cannot
    run -m venv, so the interpreter shipped alongside the app is used instead.
    Its version always matches the one Buzz was frozen with, which matters
    because the CUDA wheels are ABI-specific.

    Returns None when no interpreter of the right version is available — the
    AppImage bundle ships no separate interpreter, and the host's `python3` is
    whatever the distro installed (Ubuntu 26.04 ships 3.14, which has no torch
    wheels at all). uv can download a matching one in that case; see
    _create_cuda_env.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller extracts bundled data to sys._MEIPASS (_internal dir)
        internal_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        python_name = "python.exe" if sys.platform == "win32" else "python3"
        bundled_python = internal_dir / "python" / python_name
        if bundled_python.is_file():
            return str(bundled_python)
        # Fallback: look in PATH, but only for an interpreter of our version.
        version = get_python_version()
        for candidate in (f"python{version}", "python3", "python"):
            python = shutil.which(candidate)
            if python and _interpreter_version_matches(python):
                return python
        logger.info(
            "No Python %s interpreter found in PATH for the CUDA environment", version
        )
        return None

    # Inside a venv, base_executable is the interpreter the venv was built from;
    # deriving the new venv from it avoids chaining venvs.
    return getattr(sys, "_base_executable", None) or sys.executable


def _find_uv() -> str | None:
    """Return the path of a usable uv binary, or None.

    The snap ships uv (stage-snaps in snap/snapcraft.yaml) and its Python has
    neither pip nor ensurepip, so uv is the only way to create the venv there.
    """
    candidates = []
    snap_dir = os.environ.get("SNAP")
    if snap_dir:
        candidates.append(str(Path(snap_dir) / "bin" / "uv"))
    found = shutil.which("uv")
    if found:
        candidates.append(found)

    for candidate in candidates:
        try:
            probe = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                timeout=15,
                **_subprocess_hide_window_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            return candidate
    return None


def _venv_python(env_dir: Path) -> Path:
    """Return the interpreter path inside a venv."""
    if sys.platform == "win32":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def _create_cuda_env(env_dir: Path, progress_callback=None) -> list[str]:
    """Create the private CUDA venv and return the install command prefix.

    Two ways in, because no single one works everywhere:
    - uv, when available (the snap's Python has no pip and ensurepip is pruned
      from the snap payload, so `-m venv` cannot bootstrap one there).
    - the stdlib venv module, which bootstraps pip into the new environment.
      The bundled Windows interpreter ships the full stdlib, so this works even
      though the app directory under Program Files is not writable.
    """
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    python = _get_base_python()
    hide_kwargs = _subprocess_hide_window_kwargs()

    uv = _find_uv()
    if uv:
        # With no matching interpreter on the machine, ask uv for the version
        # instead of a path: it downloads a managed CPython of exactly that
        # version, which is what the cu129 wheels are built for.
        python_arg = python or get_python_version()
        logger.info("Creating CUDA venv with uv (%s) from %s", uv, python_arg)
        _run_command(
            [uv, "venv", "--python", python_arg, str(env_dir)],
            progress_callback=progress_callback,
            error_message="Could not create the environment for CUDA packages",
        )
        # --no-cache: the wheels are several gigabytes and are never reused,
        # so a second copy in the uv cache is pure waste.
        return [
            uv, "pip", "install", "--no-cache",
            "--python", str(_venv_python(env_dir)),
        ]

    if python is None:
        raise RuntimeError(
            f"Could not find a Python {get_python_version()} interpreter to create "
            "the environment for CUDA packages. Install Python "
            f"{get_python_version()} (or uv) and try again."
        )

    logger.info("Creating CUDA venv with %s -m venv", python)
    result = subprocess.run(
        [python, "-m", "venv", str(env_dir)],
        capture_output=True,
        text=True,
        timeout=300,
        **hide_kwargs,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Could not create the environment for CUDA packages in "
            f"{env_dir}: {(result.stderr or result.stdout or '').strip()}"
        )
    return [str(_venv_python(env_dir)), "-m", "pip", "install", "--no-cache-dir"]


def _subprocess_hide_window_kwargs() -> dict[str, Any]:
    """Return kwargs to hide the console window on Windows."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _run_command(cmd, progress_callback=None, error_message="Command failed"):
    """Run a command, streaming its output to progress_callback."""
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
        raise RuntimeError(f"{error_message} (exit code {process.returncode})")


def _run_install(install_cmd, packages, extra_args=None, progress_callback=None):
    cmd = list(install_cmd) + list(packages)
    if extra_args:
        cmd += extra_args

    _run_command(cmd, progress_callback=progress_callback, error_message="pip install failed")
