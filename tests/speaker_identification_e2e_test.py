import logging
import os
import uuid

import pytest

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from tests.audio import test_audio_path

# These tests download the alignment, punctuation and diarization models and run
# the whole speaker identification pipeline, so they only run when
# ``BUZZ_TEST_DOWNLOAD_MODELS`` is set. This keeps them out of CI (and default
# local runs) while allowing an explicit opt-in for full end-to-end checks.
# Set ``BUZZ_FORCE_CPU=true`` alongside it to check the CPU path, for example on
# machines whose GPU is too old for the CUDA kernels the diarizers ship with.
pytestmark = pytest.mark.skipif(
    os.environ.get("BUZZ_TEST_DOWNLOAD_MODELS") is None,
    reason="Set BUZZ_TEST_DOWNLOAD_MODELS to run tests that download models",
)


@pytest.fixture()
def transcription(
    qapp, transcription_dao, transcription_segment_dao
) -> Transcription:
    # ``qapp`` first: the Qt SQL driver needs a QApplication before the db fixture runs
    id = uuid.uuid4()
    transcription_dao.insert(
        Transcription(
            id=str(id),
            status="completed",
            file=test_audio_path,
            task=Task.TRANSCRIBE.value,
            model_type=ModelType.WHISPER.value,
            whisper_model_size=WhisperModelSize.SMALL.value,
        )
    )
    transcription_segment_dao.insert(TranscriptionSegment(40, 299, "Bien", "", str(id)))
    transcription_segment_dao.insert(
        TranscriptionSegment(299, 329, "venue dans", "", str(id))
    )

    return transcription_dao.find_by_id(str(id))


def make_worker(transcription, transcription_service, diarizer):
    from buzz.widgets.transcription_viewer.speaker_identification_widget import (
        IdentificationWorker,
    )

    worker = IdentificationWorker(
        transcription=transcription,
        transcription_service=transcription_service,
        diarizer=diarizer,
    )
    worker._import_libraries()
    return worker


def assert_speaker_segments(segments):
    assert isinstance(segments, list)
    assert len(segments) > 0

    for segment in segments:
        assert segment["speaker"].startswith("Speaker ")
        assert segment["text"].strip() != ""
        assert segment["start_time"] <= segment["end_time"]

    # The test audio is a single speaker saying "Bienvenue dans ..."
    assert segments[0]["speaker"] == "Speaker 0"
    normalized_text = segments[0]["text"].replace(" ", "").rstrip(".").lower()
    assert normalized_text == "bienvenuedans", segments[0]["text"]


@pytest.mark.parametrize("diarizer", ["msdd", "sortformer"])
def test_identification_steps(transcription, transcription_service, diarizer):
    """Run every speaker identification step in order, so a failure names the step.

    This mirrors ``IdentificationWorker.run`` but without the Qt thread, which
    keeps tracebacks (e.g. a CUDA "no kernel image is available" error while
    building the diarizer) attached to the step that produced them.
    """
    import torch

    worker = make_worker(transcription, transcription_service, diarizer)

    # 1/8 + 2/8 - collect transcripts and load audio
    language, full_transcript, audio_waveform = worker._get_transcript_data()
    assert language == "en"
    assert full_transcript == "Bien venue dans"
    assert len(audio_waveform) > 0

    device, torch_dtype = worker._setup_device()
    logging.info("Speaker identification test running on device=%s", device)
    assert device in ("cpu", "cuda")
    if os.getenv("BUZZ_FORCE_CPU", "false").lower() == "true":
        assert device == "cpu"
        assert torch_dtype == torch.float32

    # 3/8 - alignment model
    alignment_model, alignment_tokenizer = worker._load_alignment_model_with_retry(
        device, torch_dtype
    )
    assert alignment_model is not None
    assert alignment_tokenizer is not None

    # 4/8 - emissions (frees the alignment model on the way out)
    emissions, stride = worker._generate_emissions_and_cleanup(
        alignment_model, audio_waveform, device
    )
    assert emissions is not None
    assert stride > 0

    # 5/8 - word timestamps
    word_timestamps = worker._get_word_timestamps(
        full_transcript, language, emissions, stride, alignment_tokenizer
    )
    assert len(word_timestamps) > 0
    assert {"text", "start", "end"} <= set(word_timestamps[0].keys())

    # 6/8 - diarization
    speaker_ts = worker._run_diarization(audio_waveform, device)
    assert len(speaker_ts) > 0

    # 7/8 - speaker mapping with punctuation restoration
    ssm = worker._map_speakers_with_punctuation(
        word_timestamps, speaker_ts, language, device
    )
    assert_speaker_segments(ssm)


def test_identification_worker_run_end_to_end(
    qtbot, transcription, transcription_service
):
    """The full worker run, as the widget triggers it, emits mapped segments."""
    from buzz.widgets.transcription_viewer.speaker_identification_widget import (
        IdentificationWorker,
    )

    worker = IdentificationWorker(
        transcription=transcription,
        transcription_service=transcription_service,
    )

    results = []
    errors = []
    worker.finished.connect(results.append)
    worker.error.connect(errors.append)

    with qtbot.waitSignal(worker.finished, timeout=600000):  # 10 min timeout
        worker.run()

    assert errors == []
    assert len(results) == 1
    assert_speaker_segments(results[0])
