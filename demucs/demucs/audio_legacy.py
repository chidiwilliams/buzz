# This file is to extend support for torchaudio 2.1

import importlib
import os
import sys
import warnings

if not "torchaudio" in sys.modules:
    os.environ["TORCHAUDIO_USE_BACKEND_DISPATCHER"] = "0"
elif os.getenv("TORCHAUDIO_USE_BACKEND_DISPATCHER", default="1") == "1":
    if sys.modules["torchaudio"].__version__ >= "2.1":
        os.environ["TORCHAUDIO_USE_BACKEND_DISPATCHER"] = "0"
        importlib.reload(sys.modules["torchaudio"])
        warnings.warn(
            "TORCHAUDIO_USE_BACKEND_DISPATCHER is set to 0 and torchaudio is reloaded.",
            ImportWarning,
        )
