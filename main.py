import logging
import multiprocessing

from gui import Application

if __name__ == "__main__":
    # Starting child processes with 'fork' stops PyInstaller
    # from opening a new window for each new process
    multiprocessing.set_start_method('fork')

    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(module)s.%(funcName)s:%(lineno)d %(levelname)s -> %(message)s")

    app = Application()
    app.exec()
