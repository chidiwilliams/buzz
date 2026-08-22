import importlib.util
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication

from buzz.widgets.transcription_viewer.speaker_identification_widget import (
    IdentificationWorker,
    SpeakerIdentificationWidget,
)


# NeMo is not installed on all platforms Buzz supports (Intel macs, for example),
# so the tests that touch the vendored MSDD wrapper only run where it is available.
requires_nemo = pytest.mark.skipif(
    importlib.util.find_spec("nemo") is None,
    reason="NeMo is not installed on this platform",
)


@pytest.fixture(scope="session")
def qapp_cls():
    """These focused widget tests do not need Buzz's database-backed application."""
    return QApplication


def test_msdd_diarization_uses_known_speaker_count():
    """MSDD receives the exact speaker count selected by the user."""
    worker = IdentificationWorker(
        MagicMock(),
        MagicMock(),
        diarizer="msdd",
        num_speakers=3,
    )
    diarizer = MagicMock()
    diarizer.diarize.return_value = [(0, 1000, 0)]
    worker._MSDDDiarizer = MagicMock(return_value=diarizer)

    result = worker._run_diarization(np.zeros(160, dtype=np.float32), "cpu")

    assert result == [(0, 1000, 0)]
    worker._MSDDDiarizer.assert_called_once_with("cpu")
    assert diarizer.diarize.call_args.kwargs == {"num_speakers": 3}


def test_sortformer_diarization_does_not_receive_speaker_count():
    """Sortformer keeps its automatic speaker detection API."""
    worker = IdentificationWorker(
        MagicMock(),
        MagicMock(),
        diarizer="sortformer",
        num_speakers=3,
    )
    diarizer = MagicMock()
    diarizer.diarize.return_value = [(0, 1000, 0)]
    worker._SortformerDiarizer = MagicMock(return_value=diarizer)

    worker._run_diarization(np.zeros(160, dtype=np.float32), "cpu")

    assert diarizer.diarize.call_args.kwargs == {}


@requires_nemo
def test_msdd_wrapper_configures_nemo_with_known_speaker_count():
    """The vendored wrapper writes the count to the manifest and NeMo config."""
    from whisper_diarization.diarization.msdd import msdd

    diarizer = msdd.MSDDDiarizer.__new__(msdd.MSDDDiarizer)
    diarizer.model = MagicMock()

    with (
        patch.object(msdd.json, "dump") as dump,
        patch.object(msdd, "rttm_to_labels", return_value=["0.0 1.0 speaker_0"]),
    ):
        result = diarizer.diarize(torch.zeros((1, 160)), num_speakers=3)

    assert dump.call_args.args[0]["num_speakers"] == 3
    assert diarizer.model._initialize_configs.call_args.kwargs["num_speakers"] == 3
    assert result == [(0, 1000, 0)]


@requires_nemo
@pytest.mark.parametrize("speaker_count", [0, 9])
def test_msdd_wrapper_rejects_unsupported_speaker_count(speaker_count):
    """The wrapper rejects counts outside NeMo's configured 1-8 range."""
    from whisper_diarization.diarization.msdd.msdd import MSDDDiarizer

    diarizer = MSDDDiarizer.__new__(MSDDDiarizer)

    with pytest.raises(ValueError, match="between 1 and 8"):
        diarizer.diarize(torch.zeros((1, 160)), num_speakers=speaker_count)


def test_speaker_count_selector_defaults_to_auto(qtbot):
    """The selector offers Auto and the exact counts supported by MSDD."""
    transcription = MagicMock(file="")
    widget = SpeakerIdentificationWidget(transcription, MagicMock())
    qtbot.addWidget(widget)

    assert widget.speaker_count_combo.currentData() is None
    assert [
        widget.speaker_count_combo.itemData(index)
        for index in range(widget.speaker_count_combo.count())
    ] == [None, 2, 3, 4, 5, 6, 7, 8]

    widget.close()


def test_identify_uses_selected_speaker_count(qtbot):
    """The selected exact count is passed to the MSDD worker."""
    transcription = MagicMock(file="")
    widget = SpeakerIdentificationWidget(transcription, MagicMock())
    qtbot.addWidget(widget)
    widget.speaker_count_combo.setCurrentIndex(widget.speaker_count_combo.findData(3))

    mock_thread = MagicMock(spec=QThread)
    mock_thread.started = MagicMock()
    with (
        patch.object(widget, "_cleanup_thread"),
        patch(
            "buzz.widgets.transcription_viewer.speaker_identification_widget.QThread",
            return_value=mock_thread,
        ),
        patch.object(IdentificationWorker, "moveToThread"),
    ):
        widget.on_identify_button_clicked()

    assert widget.worker.diarizer == "msdd"
    assert widget.worker.num_speakers == 3

    widget.close()


def test_sortformer_disables_exact_speaker_count(qtbot):
    """Switching to Sortformer resets and disables the unsupported option."""
    transcription = MagicMock(file="")
    widget = SpeakerIdentificationWidget(transcription, MagicMock())
    qtbot.addWidget(widget)
    widget.speaker_count_combo.setCurrentIndex(widget.speaker_count_combo.findData(3))

    widget.sortformer_radio.setChecked(True)

    assert not widget.speaker_count_combo.isEnabled()
    assert widget.speaker_count_combo.currentData() is None

    widget.close()
