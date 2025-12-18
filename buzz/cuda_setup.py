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


def _get_nvidia_package_lib_dirs() -> list[Path]:
    """Find all nvidia package library directories in site-packages."""
    lib_dirs = []

    # Find site-packages directories
    site_packages_dirs = []
    for path in sys.path:
        if "site-packages" in path:
            site_packages_dirs.append(Path(path))

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

    # Check each site-packages for nvidia packages
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

    return lib_dirs


def _setup_windows_dll_directories():
    """Add nvidia library directories to Windows DLL search path."""
    lib_dirs = _get_nvidia_package_lib_dirs()
    for lib_dir in lib_dirs:
        try:
            os.add_dll_directory(str(lib_dir))
            logger.debug(f"Added DLL directory: {lib_dir}")
        except (OSError, AttributeError) as e:
            logger.debug(f"Could not add DLL directory {lib_dir}: {e}")


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
                logger.debug(f"Skipping library: {lib_file}")
                continue

            try:
                # Use RTLD_GLOBAL so symbols are available to other libraries
                ctypes.CDLL(str(lib_file), mode=ctypes.RTLD_GLOBAL)
                loaded_libs.add(lib_file.name)
                logger.debug(f"Preloaded library: {lib_file}")
            except OSError as e:
                # Some libraries may have missing dependencies, that's ok
                logger.debug(f"Could not preload {lib_file}: {e}")


def setup_cuda_libraries():
    """Set up CUDA library paths for the current platform.

    This function should be called as early as possible, before any torch
    or CUDA-dependent libraries are imported.
    """
    system = platform.system()

    if system == "Windows":
        _setup_windows_dll_directories()
    elif system == "Linux":
        _preload_linux_libraries()
    # macOS doesn't have CUDA support, so nothing to do


# Auto-run setup when this module is imported
setup_cuda_libraries()
