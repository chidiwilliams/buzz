import os
import sys
import platform
import subprocess
from unittest.mock import patch

import numpy as np
import pytest

from buzz.transformers_whisper import (
    TransformersTranscriber,
    is_intel_mac,
    is_peft_model,
    load_audio_input,
)


class TestIsIntelMac:
    @pytest.mark.parametrize(
        "sys_platform,machine,expected",
        [
            ("linux", "x86_64", False),
            ("win32", "x86_64", False),
            ("darwin", "arm64", False),
            ("darwin", "x86_64", True),
            ("darwin", "i386", False),
        ],
    )
    def test_is_intel_mac(self, sys_platform, machine, expected):
        with patch("buzz.transformers_whisper.sys.platform", sys_platform), \
             patch("buzz.transformers_whisper.platform.machine", return_value=machine):
            assert is_intel_mac() == expected


class TestIsPeftModel:
    @pytest.mark.parametrize(
        "model_id,expected",
        [
            ("openai/whisper-tiny-peft", True),
            ("user/model-PEFT", True),
            ("openai/whisper-tiny", False),
            ("facebook/mms-1b-all", False),
            ("", False),
        ],
    )
    def test_peft_detection(self, model_id, expected):
        assert is_peft_model(model_id) == expected


class TestGetPeftRepoId:
    def test_repo_id_returned_as_is(self):
        transcriber = TransformersTranscriber("user/whisper-tiny-peft")
        with patch("os.path.exists", return_value=False):
            assert transcriber._get_peft_repo_id() == "user/whisper-tiny-peft"

    def test_linux_cache_path(self):
        linux_path = "/home/user/.cache/Buzz/models/models--user--whisper-peft/snapshots/abc123"
        transcriber = TransformersTranscriber(linux_path)
        with patch("os.path.exists", return_value=True), \
             patch("buzz.transformers_whisper.os.sep", "/"):
            assert transcriber._get_peft_repo_id() == "user/whisper-peft"

    def test_windows_cache_path(self):
        windows_path = r"C:\Users\user\.cache\Buzz\models\models--user--whisper-peft\snapshots\abc123"
        transcriber = TransformersTranscriber(windows_path)
        with patch("os.path.exists", return_value=True), \
             patch("buzz.transformers_whisper.os.sep", "\\"):
            assert transcriber._get_peft_repo_id() == "user/whisper-peft"

    def test_fallback_returns_model_id(self):
        transcriber = TransformersTranscriber("some-local-model")
        with patch("os.path.exists", return_value=True):
            assert transcriber._get_peft_repo_id() == "some-local-model"


class TestGetMmsRepoId:
    """Tests for TransformersTranscriber._get_mms_repo_id method."""

    def test_repo_id_returned_as_is(self):
        """Test that a HuggingFace repo ID is returned unchanged."""
        transcriber = TransformersTranscriber("facebook/mms-1b-all")
        with patch("os.path.exists", return_value=False):
            assert transcriber._get_mms_repo_id() == "facebook/mms-1b-all"

    def test_linux_cache_path(self):
        """Test extraction from Linux-style cache path."""
        linux_path = "/home/user/.cache/Buzz/models/models--facebook--mms-1b-all/snapshots/abc123"
        transcriber = TransformersTranscriber(linux_path)
        with patch("os.path.exists", return_value=True), \
             patch("buzz.transformers_whisper.os.sep", "/"):
            assert transcriber._get_mms_repo_id() == "facebook/mms-1b-all"

    def test_windows_cache_path(self):
        """Test extraction from Windows-style cache path."""
        windows_path = r"C:\Users\user\.cache\Buzz\models\models--facebook--mms-1b-all\snapshots\abc123"
        transcriber = TransformersTranscriber(windows_path)
        with patch("os.path.exists", return_value=True), \
             patch("buzz.transformers_whisper.os.sep", "\\"):
            assert transcriber._get_mms_repo_id() == "facebook/mms-1b-all"

    def test_fallback_returns_model_id(self):
        """Test that model_id is returned as fallback when pattern not matched."""
        transcriber = TransformersTranscriber("some-local-model")
        with patch("os.path.exists", return_value=True):
            assert transcriber._get_mms_repo_id() == "some-local-model"

    def test_nested_org_name(self):
        """Test extraction with different org/model names."""
        linux_path = "/home/user/.cache/Buzz/models/models--openai--whisper-large-v3/snapshots/xyz"
        transcriber = TransformersTranscriber(linux_path)
        with patch("os.path.exists", return_value=True), \
             patch("buzz.transformers_whisper.os.sep", "/"):
            assert transcriber._get_mms_repo_id() == "openai/whisper-large-v3"


class TestLoadAudioInput:
    def test_passes_through_arrays(self):
        array = np.zeros(10, dtype=np.float32)
        assert load_audio_input(array, 16000) is array

    def test_loads_mp4_with_moov_atom_at_end(self, tmp_path):
        """Non-faststart MP4s must load (transformers' ffmpeg_read rejects them).

        Regression test for https://github.com/chidiwilliams/buzz/issues/1603
        """
        path = str(tmp_path / "moov-last.mp4")
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
                "-f", "lavfi", "-i", "testsrc=s=640x480:d=60:r=25",
                "-c:a", "aac", "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0",
                "-shortest", path,
            ],
            check=True,
        )

        # Guard the premise: moov must sit after mdat for this to be a real test
        data = open(path, "rb").read()
        assert data.find(b"moov") > data.find(b"mdat")

        audio = load_audio_input(path, 16000)
        assert audio.dtype == np.float32
        assert len(audio) == pytest.approx(60 * 16000, rel=0.01)
