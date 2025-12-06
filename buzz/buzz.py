import faulthandler
import logging
import multiprocessing
import os
import platform
import sys
from pathlib import Path
from typing import TextIO

from platformdirs import user_log_dir, user_cache_dir, user_data_dir

# Add CUDA libraries to LD_LIBRARY_PATH if they exist in the virtual environment
# This fixes "Unable to load libcudnn_ops.so" errors on Linux
if platform.system() == "Linux":
    try:
        # Find site-packages directory relative to this file
        site_packages = Path(__file__).parent.parent
        if site_packages.name != "site-packages":
            # We're in development mode, look for .venv
            venv_site_packages = site_packages / ".venv" / "lib"
            if venv_site_packages.exists():
                # Find pythonX.X directory
                python_dirs = list(venv_site_packages.glob("python3.*"))
                if python_dirs:
                    site_packages = python_dirs[0] / "site-packages"

        # Check for NVIDIA CUDA libraries
        cudnn_lib_path = site_packages / "nvidia" / "cudnn" / "lib"
        if cudnn_lib_path.exists() and cudnn_lib_path.is_dir():
            current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
            cudnn_lib_str = str(cudnn_lib_path)

            # Only add if not already in LD_LIBRARY_PATH
            if cudnn_lib_str not in current_ld_path:
                new_ld_path = f"{cudnn_lib_str}:{current_ld_path}" if current_ld_path else cudnn_lib_str
                os.environ["LD_LIBRARY_PATH"] = new_ld_path
                logging.debug(f"Added CUDA libraries to LD_LIBRARY_PATH: {cudnn_lib_str}")
    except Exception as e:
        # Don't fail if we can't set up CUDA paths
        logging.debug(f"Could not set up CUDA library paths: {e}")

# Will download all Huggingface data to the app cache directory
os.environ.setdefault("HF_HOME", user_cache_dir("Buzz"))

from buzz.assets import APP_BASE_DIR

# Check for segfaults if not running in frozen mode
if getattr(sys, "frozen", False) is False:
    faulthandler.enable()

# Sets stderr to no-op TextIO when None (run as Windows GUI).
# Resolves https://github.com/chidiwilliams/buzz/issues/221
if sys.stderr is None:
    sys.stderr = TextIO()

# Adds the current directory to the PATH, so the ffmpeg binary get picked up:
# https://stackoverflow.com/a/44352931/9830227
os.environ["PATH"] += os.pathsep + APP_BASE_DIR

# Add the app directory to the DLL list: https://stackoverflow.com/a/64303856
if platform.system() == "Windows":
    os.add_dll_directory(APP_BASE_DIR)

    dll_backup_dir = os.path.join(APP_BASE_DIR, "dll_backup")
    if os.path.isdir(dll_backup_dir):
        os.add_dll_directory(dll_backup_dir)

    onnx_dll_dir = os.path.join(APP_BASE_DIR, "onnxruntime", "capi")
    if os.path.isdir(onnx_dll_dir):
        os.add_dll_directory(onnx_dll_dir)


def main():
    if platform.system() == "Linux":
        multiprocessing.set_start_method("spawn")

    # Fixes opening new window when app has been frozen on Windows:
    # https://stackoverflow.com/a/33979091
    multiprocessing.freeze_support()

    log_dir = user_log_dir(appname="Buzz")
    os.makedirs(log_dir, exist_ok=True)

    log_format = (
        "[%(asctime)s] %(module)s.%(funcName)s:%(lineno)d %(levelname)s -> %(message)s"
    )
    logging.basicConfig(
        filename=os.path.join(log_dir, "logs.txt"),
        level=logging.DEBUG,
        format=log_format,
    )

    # Silence noisy third-party library loggers
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("graphviz").setLevel(logging.WARNING)
    logging.getLogger("nemo_logger").setLevel(logging.ERROR)
    logging.getLogger("nemo_logging").setLevel(logging.ERROR)
    logging.getLogger("numba").setLevel(logging.WARNING)
    logging.getLogger("torio._extension.utils").setLevel(logging.WARNING)
    logging.getLogger("export_config_manager").setLevel(logging.WARNING)
    logging.getLogger("training_telemetry_provider").setLevel(logging.ERROR)
    logging.getLogger("default_recorder").setLevel(logging.WARNING)
    logging.getLogger("config").setLevel(logging.WARNING)

    if getattr(sys, "frozen", False) is False:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(stdout_handler)

    from buzz.cli import parse_command_line
    from buzz.widgets.application import Application

    logging.debug("app_dir: %s", APP_BASE_DIR)
    logging.debug("log_dir: %s", log_dir)
    logging.debug("cache_dir: %s", user_cache_dir("Buzz"))
    logging.debug("data_dir: %s", user_data_dir("Buzz"))

    app = Application(sys.argv)
    parse_command_line(app)
    app.show_main_window()
    sys.exit(app.exec())
