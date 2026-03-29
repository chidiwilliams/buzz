"""
CUDA library path setup for nvidia packages installed via pip.

This module must be imported BEFORE any torch or CUDA-dependent libraries are imported.
It handles locating and loading CUDA libraries (cuDNN, cuBLAS, etc.) from the nvidia
pip packages.

On Windows: Uses os.add_dll_directory() to add library paths
On Linux: Re-execs the process with LD_LIBRARY_PATH set when cuda_packages are present,
          then preloads libraries with RTLD_GLOBAL for any remaining gaps.
On macOS: No action needed (CUDA not supported)
"""

import ctypes
import logging
import os
import platform
import sys
from pathlib import Path


logger = logging.getLogger(__name__)


def _get_cuda_target_dir() -> Path | None:
    """Return the --target directory used during CUDA install for snap/flatpak, or None."""
    snap_user_data = os.environ.get("SNAP_USER_DATA")
    if snap_user_data:
        return Path(snap_user_data) / "cuda_packages"
    flatpak_id = os.environ.get("FLATPAK_ID")
    if flatpak_id:
        xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(xdg_data) / "buzz" / "cuda_packages"
    return None


def _get_site_packages_dirs() -> list[Path]:
    """Return all site-packages directories, including user site-packages."""
    site_packages_dirs = []
    import site

    # For snap/flatpak, packages are installed to an explicit --target directory
    cuda_target = _get_cuda_target_dir()
    if cuda_target and cuda_target.exists():
        if str(cuda_target) not in sys.path:
            sys.path.insert(0, str(cuda_target))
        site_packages_dirs.append(cuda_target)
        logger.info("CUDA target dir (snap/flatpak): %s", cuda_target)

    user_site = site.getusersitepackages()
    if user_site:
        user_site_path = Path(user_site)
        site_packages_dirs.append(user_site_path)
        logger.info("User site-packages: %s (exists=%s)", user_site_path, user_site_path.exists())
        # Ensure user site-packages is on sys.path so torch can be imported
        if str(user_site_path) not in sys.path and user_site_path.exists():
            sys.path.insert(0, str(user_site_path))
            logger.info("Added user site-packages to sys.path: %s", user_site_path)
    for path in sys.path:
        if "site-packages" in path:
            site_packages_dirs.append(Path(path))

    return site_packages_dirs


def _get_nvidia_package_lib_dirs() -> list[Path]:
    """Find all nvidia package library directories in site-packages."""
    lib_dirs = []

    site_packages_dirs = _get_site_packages_dirs()

    # Also check relative to the current module for frozen apps
    if getattr(sys, "frozen", False):
        # For frozen apps, check the _internal directory
        frozen_lib_dir = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(sys.executable).parent
        nvidia_dir = frozen_lib_dir / "nvidia"
        if nvidia_dir.exists():
            for pkg_dir in nvidia_dir.iterdir():
                if pkg_dir.is_dir():
                    lib_subdir = pkg_dir / "lib"
                    if lib_subdir.exists():
                        lib_dirs.append(lib_subdir)
                    # Some packages have bin directory on Windows
                    bin_subdir = pkg_dir / "bin"
                    if bin_subdir.exists():
                        lib_dirs.append(bin_subdir)

    # Check each site-packages for nvidia packages AND torch/lib
    for sp_dir in site_packages_dirs:
        nvidia_dir = sp_dir / "nvidia"
        if nvidia_dir.exists():
            for pkg_dir in nvidia_dir.iterdir():
                if pkg_dir.is_dir():
                    lib_subdir = pkg_dir / "lib"
                    if lib_subdir.exists():
                        lib_dirs.append(lib_subdir)
                    # Some packages have bin directory on Windows
                    bin_subdir = pkg_dir / "bin"
                    if bin_subdir.exists():
                        lib_dirs.append(bin_subdir)
        # torch/lib contains torch_cuda and other CUDA-related DLLs
        torch_lib_dir = sp_dir / "torch" / "lib"
        if torch_lib_dir.exists():
            lib_dirs.append(torch_lib_dir)

    return lib_dirs


def _setup_windows_dll_directories():
    """Add nvidia library directories to Windows DLL search path."""
    lib_dirs = _get_nvidia_package_lib_dirs()
    if not lib_dirs:
        logger.warning("CUDA setup: no nvidia/torch library directories found")
    for lib_dir in lib_dirs:
        try:
            os.add_dll_directory(str(lib_dir))
            logger.info("CUDA setup: added DLL directory: %s", lib_dir)
        except (OSError, AttributeError) as e:
            logger.warning("CUDA setup: failed to add DLL directory %s: %s", lib_dir, e)


def _collect_cuda_lib_dirs(cuda_target: Path) -> list[str]:
    """Return all library directories under cuda_packages as strings."""
    lib_dirs: list[str] = []

    torch_lib = cuda_target / "torch" / "lib"
    if torch_lib.exists():
        lib_dirs.append(str(torch_lib))

    nvidia_dir = cuda_target / "nvidia"
    if nvidia_dir.exists():
        for pkg_dir in sorted(nvidia_dir.iterdir()):
            if pkg_dir.is_dir():
                lib_subdir = pkg_dir / "lib"
                if lib_subdir.exists():
                    lib_dirs.append(str(lib_subdir))

    return lib_dirs


def _setup_linux_cuda():
    """Set up CUDA libraries on Linux for snap/flatpak CUDA installs.

    LD_LIBRARY_PATH is read by the dynamic linker only at process start, so
    preloading individual .so files with ctypes is fragile: if *any* library
    in the dependency chain (e.g. libcusparseLt.so.0 → libcuda.so.1) is not
    yet in the search path, the load silently fails, and later imports of torch
    or torchaudio crash with "cannot open shared object file".

    The reliable fix is to re-exec the current process with LD_LIBRARY_PATH
    extended to include all cuda_packages lib dirs.  After re-exec the dynamic
    linker finds every CUDA library via the standard search path for the
    entire lifetime of the process.

    A sentinel value in LD_LIBRARY_PATH prevents infinite re-exec loops.
    """
    # Ensure cuda_packages is on sys.path so Python can import torch
    _get_site_packages_dirs()

    cuda_target = _get_cuda_target_dir()
    if cuda_target is None or not cuda_target.exists():
        logger.debug("CUDA setup: no cuda_packages dir found, skipping")
        return

    torch_lib = cuda_target / "torch" / "lib"
    if not torch_lib.exists():
        logger.debug("CUDA setup: no torch/lib in cuda_packages, skipping")
        return

    sentinel = str(torch_lib)
    current_ld = os.environ.get("LD_LIBRARY_PATH", "")

    if sentinel in current_ld.split(":"):
        # Already re-exec'd (or user manually set the path) — nothing to do
        logger.info("CUDA setup: LD_LIBRARY_PATH already contains cuda torch/lib, proceeding")
        return

    # Build new LD_LIBRARY_PATH: cuda_packages lib dirs prepended to existing path
    extra_dirs = _collect_cuda_lib_dirs(cuda_target)
    new_ld = ":".join(extra_dirs)
    if current_ld:
        new_ld = new_ld + ":" + current_ld
    os.environ["LD_LIBRARY_PATH"] = new_ld

    # Re-exec the process so the dynamic linker picks up the new LD_LIBRARY_PATH.
    # We read the original argv from /proc/self/cmdline to preserve the exact
    # invocation (works for both `python -m buzz` and frozen binaries).
    try:
        with open("/proc/self/cmdline", "rb") as f:
            raw_args = [a.decode("utf-8", errors="replace") for a in f.read().split(b"\x00") if a]
        executable = raw_args[0]
        logger.info("CUDA setup: re-execing %s with LD_LIBRARY_PATH=%s", executable, new_ld)
        os.execv(executable, raw_args)
    except Exception as e:
        # Re-exec failed (e.g. AppArmor restriction) — fall back to ctypes preloading
        logger.warning("CUDA setup: re-exec failed (%s), falling back to ctypes preload", e)
        _preload_linux_libraries_fallback()


def _preload_linux_libraries_fallback():
    """Fallback: preload CUDA .so files with RTLD_GLOBAL when re-exec is not possible."""
    lib_dirs = _get_nvidia_package_lib_dirs()
    skip_patterns = ["libnvblas"]
    candidates = []
    for lib_dir in lib_dirs:
        if not lib_dir.exists():
            continue
        for lib_file in sorted(lib_dir.glob("*.so*")):
            if lib_file.is_symlink() and not lib_file.exists():
                continue
            if any(p in lib_file.name for p in skip_patterns):
                continue
            candidates.append(lib_file)

    loaded: set[str] = set()
    for pass_num in range(5):
        newly = 0
        for lib_file in candidates:
            if lib_file.name in loaded:
                continue
            try:
                ctypes.CDLL(str(lib_file), mode=ctypes.RTLD_GLOBAL)
                loaded.add(lib_file.name)
                newly += 1
            except OSError as e:
                logger.debug("Preload pass %d: skipping %s: %s", pass_num + 1, lib_file.name, e)
        logger.info("Preload pass %d: +%d libs (%d total)", pass_num + 1, newly, len(loaded))
        if newly == 0:
            break


def setup_cuda_libraries():
    """Set up CUDA library paths for the current platform.

    This function should be called as early as possible, before any torch
    or CUDA-dependent libraries are imported.
    """
    system = platform.system()
    logger.info("CUDA setup: platform=%s, frozen=%s", system, getattr(sys, "frozen", False))

    if system == "Windows":
        _setup_windows_dll_directories()
    elif system == "Linux":
        _setup_linux_cuda()
    # macOS doesn't have CUDA support, so nothing to do

    logger.info("CUDA setup: complete")


# Auto-run setup when this module is imported
setup_cuda_libraries()
