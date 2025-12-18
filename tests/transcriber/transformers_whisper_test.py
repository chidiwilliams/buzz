import os
from unittest.mock import patch

import pytest

from buzz.transformers_whisper import TransformersTranscriber


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
