import logging

from gui import Application

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(module)s.%(funcName)s:%(lineno)d %(levelname)s -> %(message)s")

app = Application()
app.exec()
