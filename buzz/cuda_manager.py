"""
Utilities for checking and installing CUDA support at runtime.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Pinned CUDA torch versions for in-app installation
CUDA_INDEX_URL = "https://download.pytorch.org/whl/cu129"
CUDA_TORCH_PACKAGES = [
    "torch==2.8.0+cu129",
    "torchaudio==2.8.0+cu129",
]
CUDA_NVIDIA_PACKAGES = [
    "nvidia-cublas-cu12==12.9.1.4",
    "nvidia-cuda-cupti-cu12==12.9.79",
    "nvidia-cuda-runtime-cu12==12.9.79",
]
CUDA_NVIDIA_INDEX_URL = "https://pypi.ngc.nvidia.com"


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
        return torch.cuda.is_available()
    except ImportError:
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
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Fallback: kernel driver version file — present when NVIDIA driver is loaded
    return Path("/proc/driver/nvidia/version").exists()


def install_cuda(progress_callback=None):
    """
    Install CUDA-enabled torch and nvidia libraries into user site-packages.

    Args:
        progress_callback: Optional callable(str) called with status messages.
    """
    def report(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    report("Installing CUDA-enabled PyTorch...")
    _pip_install(
        CUDA_TORCH_PACKAGES,
        extra_args=["--index-url", CUDA_INDEX_URL, "--user"],
        progress_callback=report,
    )

    report("Installing NVIDIA CUDA libraries...")
    _pip_install(
        CUDA_NVIDIA_PACKAGES,
        extra_args=["--extra-index-url", CUDA_NVIDIA_INDEX_URL, "--user"],
        progress_callback=report,
    )

    report("CUDA installation complete. Please restart Buzz to enable GPU acceleration.")


def _pip_install(packages, extra_args=None, progress_callback=None):
    cmd = [sys.executable, "-m", "pip", "install"] + packages
    if extra_args:
        cmd += extra_args

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in process.stdout:
        line = line.rstrip()
        if line and progress_callback:
            progress_callback(line)

    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"pip install failed with exit code {process.returncode}")
