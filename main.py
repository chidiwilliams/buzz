import logging
import multiprocessing

from gui import Application

if __name__ == "__main__":
    # Stop PyInstaller from randomly opening multiple windows: https://stackoverflow.com/a/32677108/9830227
    multiprocessing.freeze_support()

    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(module)s.%(funcName)s:%(lineno)d %(levelname)s -> %(message)s")

    app = Application()
    app.exec()
