from dataclasses import dataclass


SPEAKER_COLORS = (
    "#1976D2",
    "#C62828",
    "#2E7D32",
    "#6A1B9A",
    "#EF6C00",
    "#00838F",
    "#AD1457",
    "#5D4037",
    "#455A64",
    "#558B2F",
    "#283593",
    "#9E6C00",
)


@dataclass
class SpeakerGroup:
    speaker: str
    text: str
    start_time: int
    end_time: int


def group_speaker_segments(
    segments,
    paragraph_split_time: int = 2000,
) -> tuple[list[SpeakerGroup], list[str]]:
    """Group adjacent segments exactly as the Speakers view displays them."""
    groups: list[SpeakerGroup] = []
    speaker_order: list[str] = []

    for segment in segments:
        speaker = (segment.speaker or "").strip()
        text = (segment.text or "").strip()
        if speaker and speaker not in speaker_order:
            speaker_order.append(speaker)

        if groups and groups[-1].speaker == speaker:
            if text:
                separator = (
                    "\n"
                    if segment.start_time - groups[-1].end_time
                    >= paragraph_split_time
                    else " "
                )
                groups[-1].text += separator + text
            groups[-1].end_time = segment.end_time
        else:
            groups.append(
                SpeakerGroup(
                    speaker=speaker,
                    text=text,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                )
            )

    return groups, speaker_order
