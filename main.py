import logging
import multiprocessing
import os

from appdirs import user_log_dir

from gui import Application

if __name__ == "__main__":
    # Starting child processes with 'fork' stops PyInstaller
    # from opening a new window for each new process
    multiprocessing.set_start_method('fork')

    log_dir = user_log_dir(appname='Buzz')
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, 'logs.txt'),
        level=logging.DEBUG,
        format="[%(asctime)s] %(module)s.%(funcName)s:%(lineno)d %(levelname)s -> %(message)s")

    app = Application()
    app.exec()
