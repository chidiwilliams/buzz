from pathlib import Path
from unittest.mock import Mock

import pytest

from buzz.transcriber.file_transcriber import FileTranscriber, _downloaded_file_path
from buzz.transcriber.transcriber import (
    FileTranscriptionOptions,
    FileTranscriptionTask,
    TranscriptionOptions,
)


class ConcreteFileTranscriber(FileTranscriber):
    def transcribe(self):
        return []

    def stop(self):
        pass


def make_transcriber() -> ConcreteFileTranscriber:
    return ConcreteFileTranscriber(
        FileTranscriptionTask(
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="",
            url="https://example.com/video",
            source=FileTranscriptionTask.Source.URL_IMPORT,
        )
    )


@pytest.mark.parametrize(
    "title",
    [
        "中文标题 | QVD-123.",
        "foo:bar?.wav",
        "trailing-dot.",
        "trailing-space ",
        "emoji-🚀",
    ],
)
def test_url_download_uses_reported_path_instead_of_title(
    monkeypatch, tmp_path, title
):
    transcriber = make_transcriber()
    calls = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            calls["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def extract_info(self, url, download):
            calls["extract_info"] = (url, download)
            downloaded_file = tmp_path / "actual-yt-dlp-output.m4a"
            downloaded_file.write_bytes(b"downloaded audio")
            return {
                "title": title,
                "requested_downloads": [{"filepath": str(downloaded_file)}],
            }

    def fake_run(command, **_kwargs):
        calls["ffmpeg"] = command
        Path(command[-1]).write_bytes(b"wav audio")
        return Mock(returncode=0, stderr=b"")

    monkeypatch.setattr("buzz.transcriber.file_transcriber.YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr("buzz.transcriber.file_transcriber.subprocess.run", fake_run)

    assert transcriber._download_from_url()

    assert calls["extract_info"] == (transcriber.transcription_task.url, True)
    assert Path(calls["options"]["outtmpl"]).name == "source.%(ext)s"
    assert calls["ffmpeg"][calls["ffmpeg"].index("-i") + 1] == str(
        tmp_path / "actual-yt-dlp-output.m4a"
    )
    assert Path(transcriber.transcription_task.file_path).is_file()
    assert Path(transcriber.transcription_task.file_path).name == "audio.wav"
    assert transcriber.transcription_task.display_name == title
    assert title not in " ".join(calls["ffmpeg"])


def test_downloaded_file_path_rejects_missing_reported_file(tmp_path):
    missing = tmp_path / "missing.webm"

    with pytest.raises(
        FileNotFoundError, match=r"yt-dlp output does not exist: .*missing\.webm"
    ):
        _downloaded_file_path({"filepath": str(missing)})


def test_url_download_rejects_ffmpeg_failure_with_empty_stderr(
    monkeypatch, tmp_path
):
    transcriber = make_transcriber()
    error = Mock()
    transcriber.error.connect(error)
    downloaded_file = tmp_path / "CVSS9#"
    downloaded_file.write_bytes(b"downloaded audio")

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def extract_info(self, _url, download):
            assert download
            return {"filepath": str(downloaded_file)}

    monkeypatch.setattr("buzz.transcriber.file_transcriber.YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(
        "buzz.transcriber.file_transcriber.subprocess.run",
        Mock(return_value=Mock(returncode=1, stderr=b"")),
    )

    assert not transcriber._download_from_url()

    assert transcriber.transcription_task.file_path is None
    error.assert_called_once_with(
        "Error processing downloaded audio: ffmpeg exited with code 1"
    )


def test_url_download_rejects_missing_ffmpeg_output(monkeypatch, tmp_path):
    transcriber = make_transcriber()
    error = Mock()
    transcriber.error.connect(error)
    downloaded_file = tmp_path / "CVSS9#"
    downloaded_file.write_bytes(b"downloaded audio")

    class FakeYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def extract_info(self, _url, download):
            assert download
            return {"filepath": str(downloaded_file)}

    monkeypatch.setattr("buzz.transcriber.file_transcriber.YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(
        "buzz.transcriber.file_transcriber.subprocess.run",
        Mock(return_value=Mock(returncode=0, stderr=b"")),
    )

    assert not transcriber._download_from_url()

    assert transcriber.transcription_task.file_path is None
    error.assert_called_once()
    assert error.call_args.args[0].startswith("FFmpeg output does not exist:")
