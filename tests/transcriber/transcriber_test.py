import pathlib

import pytest

from buzz.transcriber.file_transcriber import write_output, to_timestamp
from buzz.transcriber.transcriber import (
    OutputFormat,
    Segment,
)


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == "00:00:00.000"
        assert to_timestamp(123456789) == "34:17:36.789"


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
