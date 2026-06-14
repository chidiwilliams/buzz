import websockets
print("websockets", websockets.__version__, "OK")

import sys
sys.path.insert(0, ".")
# Also verify the server module imports without error
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtCore import QCoreApplication
app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
from buzz.transcriber.renamer_server import _build_config, _plan_to_dict, _plan_from_dict
print("renamer_server imports OK")
