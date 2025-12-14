import faulthandler
import logging
import multiprocessing
import os
import platform
import sys
from pathlib import Path
from typing import TextIO

# Set up CUDA library paths before any torch imports
# This must happen before platformdirs or any other imports that might indirectly load torch
import buzz.cuda_setup  # noqa: F401

from platformdirs import user_log_dir, user_cache_dir, user_data_dir

# Will download all Huggingface data to the app cache directory
os.environ.setdefault("HF_HOME", user_cache_dir("Buzz"))

from buzz.assets import APP_BASE_DIR

# Check for segfaults if not running in frozen mode
# Note: On Windows, faulthandler can print "Windows fatal exception" messages
# for non-fatal RPC errors (0x800706be) during multiprocessing operations.
# These are usually harmless but noisy, so we disable faulthandler on Windows.
if getattr(sys, "frozen", False) is False and platform.system() != "Windows":
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
