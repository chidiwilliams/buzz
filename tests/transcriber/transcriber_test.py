import pathlib

import pytest

from buzz.model_loader import TranscriptionModel
from buzz.transcriber.file_transcriber import write_output, to_timestamp
from buzz.transcriber.transcriber import (
    get_output_file_path,
    OutputFormat,
    Segment,
    Task,
)


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == "00:00:00.000"
        assert to_timestamp(123456789) == "34:17:36.789"


def test_url_output_path_uses_safe_display_name(tmp_path):
    title = "中文 | test?."

    output_path = get_output_file_path(
        file_path=str(tmp_path / "audio.wav"),
        task=Task.TRANSCRIBE,
        language=None,
        model=TranscriptionModel(),
        output_format=OutputFormat.SRT,
        export_file_name_template="{{ input_file_name }}",
        display_name=title,
    )

    assert title == "中文 | test?."
    assert pathlib.Path(output_path).name == "中文 _ test_#.srt"


@pytest.mark.parametrize(
    "output_format,output_text",
    [
        (OutputFormat.TXT, "Bien venue dans "),
        (
            OutputFormat.SRT,
            "1\n00:00:00,040 --> 00:00:00,299\nBien\n\n2\n00:00:00,299 --> 00:00:00,329\nvenue dans\n\n",
        ),
        (
            OutputFormat.VTT,
            "WEBVTT\n\n00:00:00.040 --> 00:00:00.299\nBien\n\n00:00:00.299 --> 00:00:00.329\nvenue dans\n\n",
        ),
    ],
)
def test_write_output(
    tmp_path: pathlib.Path, output_format: OutputFormat, output_text: str
):
    output_file_path = tmp_path / "whisper.txt"
    segments = [Segment(40, 299, "Bien"), Segment(299, 329, "venue dans")]

    write_output(
        path=str(output_file_path), segments=segments, output_format=output_format
    )

    with open(output_file_path, encoding="utf-8") as output_file:
        assert output_text == output_file.read()
