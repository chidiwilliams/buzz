"""Run speaker identification outside the transcription viewer.

Folder watch transcriptions are exported without any user interaction, so the
diarization has to run headless, straight on the segments returned by the
transcriber and before the output files are written.
"""

import logging
from typing import Dict, List, Optional

from buzz.transcriber.transcriber import Segment


def build_speaker_segments(
    identification_result: List[Dict],
    speaker_mapping: Optional[Dict[str, str]] = None,
    merge_speaker_sentences: bool = True,
) -> List[Segment]:
    """Turn the diarization result into segments carrying speaker labels."""
    speaker_mapping = speaker_mapping or {}

    segments: List[Segment] = []
    previous_segment = None

    for entry in identification_result:
        speaker_name = speaker_mapping.get(entry["speaker"], entry["speaker"])

        if merge_speaker_sentences:
            if previous_segment and previous_segment["speaker"] == speaker_name:
                previous_segment["end_time"] = entry["end_time"]
                previous_segment["text"] += " " + entry["text"]
                continue

            if previous_segment:
                segments.append(
                    Segment(
                        start=previous_segment["start_time"],
                        end=previous_segment["end_time"],
                        text=previous_segment["text"],
                        speaker=previous_segment["speaker"],
                    )
                )

            previous_segment = {
                "start_time": entry["start_time"],
                "end_time": entry["end_time"],
                "speaker": speaker_name,
                "text": entry["text"],
            }
        else:
            segments.append(
                Segment(
                    start=entry["start_time"],
                    end=entry["end_time"],
                    text=entry["text"],
                    speaker=speaker_name,
                )
            )

    if previous_segment:
        segments.append(
            Segment(
                start=previous_segment["start_time"],
                end=previous_segment["end_time"],
                text=previous_segment["text"],
                speaker=previous_segment["speaker"],
            )
        )

    return segments


def identify_speakers(
    file_path: str,
    segments: List[Segment],
    language: Optional[str] = None,
    diarizer: str = "msdd",
    num_speakers: Optional[int] = None,
    merge_speaker_sentences: bool = True,
) -> List[Segment]:
    """Label ``segments`` with automatic speaker names.

    Runs synchronously on the calling thread. Returns the original segments
    unchanged if the identification fails, so a transcription is still
    exported when speakers cannot be identified.
    """
    if not segments:
        return segments

    # Imported here to keep the heavy diarization dependencies out of the
    # startup path of apps that never identify speakers.
    from buzz.widgets.transcription_viewer.speaker_identification_widget import (
        IdentificationWorker,
    )

    worker = IdentificationWorker(
        transcription=None,
        transcription_service=None,
        diarizer=diarizer,
        num_speakers=num_speakers if diarizer == "msdd" else None,
        segments=segments,
        file_path=file_path,
        language=language,
    )

    result: List[Dict] = []
    errors: List[str] = []

    worker.finished.connect(result.extend)
    worker.error.connect(errors.append)
    worker.progress_update.connect(
        lambda progress: logging.debug("Speaker identification: %s", progress)
    )

    try:
        worker.run()
    except Exception:
        logging.exception("Speaker identification failed")
        return segments

    if errors:
        logging.warning("Speaker identification failed: %s", errors[0])
        return segments

    if not result:
        logging.warning("Speaker identification returned no speakers")
        return segments

    return build_speaker_segments(
        result, merge_speaker_sentences=merge_speaker_sentences
    )
