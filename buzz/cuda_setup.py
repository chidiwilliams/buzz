"""
CUDA library path setup for nvidia packages installed via pip.

This module must be imported BEFORE any torch or CUDA-dependent libraries are imported.
It handles locating and loading CUDA libraries (cuDNN, cuBLAS, etc.) from the nvidia
pip packages.

On Windows: Uses os.add_dll_directory() to add library paths
On Linux: Uses ctypes to preload libraries (LD_LIBRARY_PATH is read at process start)
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


def _preload_linux_libraries():
    """Preload CUDA libraries on Linux using ctypes.

    On Linux, LD_LIBRARY_PATH is only read at process start, so we need to
    manually load the libraries using ctypes before torch tries to load them.
    """
    lib_dirs = _get_nvidia_package_lib_dirs()

    # Libraries to skip - NVBLAS requires special configuration and causes issues
    skip_patterns = ["libnvblas"]

    loaded_libs = set()

    for lib_dir in lib_dirs:
        if not lib_dir.exists():
            continue

        # Find all .so files in the directory
        for lib_file in sorted(lib_dir.glob("*.so*")):
            if lib_file.name in loaded_libs:
                continue
            if lib_file.is_symlink() and not lib_file.exists():
                continue

            # Skip problematic libraries
            if any(pattern in lib_file.name for pattern in skip_patterns):
                continue

            try:
                # Use RTLD_GLOBAL so symbols are available to other libraries
                ctypes.CDLL(str(lib_file), mode=ctypes.RTLD_GLOBAL)
                loaded_libs.add(lib_file.name)
            except OSError as e:
                # Some libraries may have missing dependencies, that's ok
                pass


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
        _preload_linux_libraries()
    # macOS doesn't have CUDA support, so nothing to do

    logger.info("CUDA setup: complete")


# Auto-run setup when this module is imported
setup_cuda_libraries()
