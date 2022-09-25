import logging
import warnings

from gui import Application

logging.basicConfig(level=logging.DEBUG)
warnings.filterwarnings('ignore')

app = Application()
app.exec()
