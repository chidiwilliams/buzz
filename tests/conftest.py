import os
import platform
import random
import string
from pathlib import Path

import pytest
from PyQt6.QtSql import QSqlDatabase
from _pytest.fixtures import SubRequest

# Set up CUDA library paths before importing any modules that might use CUDA
# This fixes "Unable to load libcudnn_ops.so" errors during tests
def setup_cuda_library_paths():
    """Configure CUDA library paths for the current platform."""
    try:
        # Find site-packages directory - in test environment, we're in the project root
        project_root = Path(__file__).parent.parent

        # Look for .venv directory
        if platform.system() == "Windows":
            venv_site_packages = project_root / ".venv" / "Lib" / "site-packages"
        else:
            venv_lib = project_root / ".venv" / "lib"
            if venv_lib.exists():
                # Find pythonX.X directory
                python_dirs = list(venv_lib.glob("python3.*"))
                if python_dirs:
                    venv_site_packages = python_dirs[0] / "site-packages"
                else:
                    return
            else:
                return

        if not venv_site_packages.exists():
            return

        # Check for NVIDIA CUDA libraries
        cudnn_lib_path = venv_site_packages / "nvidia" / "cudnn" / "lib"
        if cudnn_lib_path.exists() and cudnn_lib_path.is_dir():
            cudnn_lib_str = str(cudnn_lib_path)

            if platform.system() == "Linux":
                # Use LD_LIBRARY_PATH on Linux
                current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
                if cudnn_lib_str not in current_ld_path:
                    new_ld_path = f"{cudnn_lib_str}:{current_ld_path}" if current_ld_path else cudnn_lib_str
                    os.environ["LD_LIBRARY_PATH"] = new_ld_path
                    print(f"Test setup: Added CUDA libraries to LD_LIBRARY_PATH: {cudnn_lib_str}")
            elif platform.system() == "Windows":
                # Use os.add_dll_directory on Windows (Python 3.8+)
                try:
                    os.add_dll_directory(cudnn_lib_str)
                    print(f"Test setup: Added CUDA libraries to DLL search path: {cudnn_lib_str}")
                except (AttributeError, OSError):
                    # Fallback to PATH if add_dll_directory fails
                    current_path = os.environ.get("PATH", "")
                    if cudnn_lib_str not in current_path:
                        os.environ["PATH"] = f"{cudnn_lib_str}{os.pathsep}{current_path}"
                        print(f"Test setup: Added CUDA libraries to PATH: {cudnn_lib_str}")
    except Exception as e:
        # Don't fail if we can't set up CUDA paths
        print(f"Test setup: Could not set up CUDA library paths: {e}")

# Call this before any other imports
setup_cuda_library_paths()

from buzz.db.dao.transcription_dao import TranscriptionDAO
from buzz.db.dao.transcription_segment_dao import TranscriptionSegmentDAO
from buzz.db.db import setup_test_db
from buzz.db.service.transcription_service import TranscriptionService
from buzz.settings.settings import Settings
from buzz.settings.shortcuts import Shortcuts
from buzz.widgets.application import Application


@pytest.fixture()
def db() -> QSqlDatabase:
    db = setup_test_db()
    yield db
    db.close()
    os.remove(db.databaseName())


@pytest.fixture()
def transcription_dao(db, request: SubRequest) -> TranscriptionDAO:
    dao = TranscriptionDAO(db)
    if hasattr(request, "param"):
        transcriptions = request.param
        for transcription in transcriptions:
            dao.insert(transcription)
    return dao


@pytest.fixture()
def transcription_service(
    transcription_dao, transcription_segment_dao
) -> TranscriptionService:
    return TranscriptionService(transcription_dao, transcription_segment_dao)


@pytest.fixture()
def transcription_segment_dao(db) -> TranscriptionSegmentDAO:
    return TranscriptionSegmentDAO(db)


@pytest.fixture(scope="session")
def qapp_cls():
    return Application


@pytest.fixture(scope="session")
def qapp_args(request):
    if not hasattr(request, "param"):
        return []

    return request.param


@pytest.fixture(scope="session")
def settings():
    application = "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(6)
    )

    settings = Settings(application=application)
    yield settings
    settings.clear()


@pytest.fixture(scope="session")
def shortcuts(settings):
    return Shortcuts(settings)
