import faulthandler
import logging
import os
import sys

from appdirs import user_log_dir

from gui import Application

# Check for segfaults if not running in frozen mode
if getattr(sys, 'frozen', False) is False:
    faulthandler.enable()


# Adds the current directory to the PATH, so the ffmpeg binary get picked up:
# https://stackoverflow.com/a/44352931/9830227
app_dir = getattr(sys, '_MEIPASS', os.path.dirname(
    os.path.abspath(__file__)))
os.environ["PATH"] += os.pathsep + app_dir


def init():
    log_dir = user_log_dir(appname='Buzz')
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, 'logs.txt'),
        level=logging.DEBUG,
        format="[%(asctime)s] %(module)s.%(funcName)s:%(lineno)d %(levelname)s -> %(message)s")


if __name__ == "__main__":
    init()
    app = Application()
    sys.exit(app.exec())
