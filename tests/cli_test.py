import os
from tempfile import mkdtemp

import pytest
from pytestqt.qtbot import QtBot

from buzz.cli import (
    CommandLineModelType,
    _normalize_transcription_request,
    _resolve_model,
    parse_command_line,
)
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from tests.audio import test_audio_path, test_multibyte_utf8_audio_path


class TestCLI:
    # A batch of more than one file also covers the single file case. The app
    # closes its database when the CLI run finishes, so only one CLI test can
    # run per pytest process.
    @pytest.mark.parametrize(
        "qapp_args",
        [
            pytest.param(
                [
                    "main.py",
                    "add",
                    "--task",
                    "transcribe",
                    "--model-size",
                    "tiny",
                    "--output-directory",
                    mkdtemp(),
                    "--txt",
                    test_audio_path,
                    test_multibyte_utf8_audio_path,
                ],
            )
        ],
        indirect=True,
    )
    def test_cli_multiple_files(self, qapp, qapp_args, qtbot: QtBot):
        """Every file in a batch must be transcribed, not just the first one.
        """
        output_directory = qapp_args[7]

        parse_command_line(qapp)

        def all_outputs_exist():
            outputs = [
                file for file in os.listdir(output_directory) if file.endswith(".txt")
            ]
            assert len(outputs) == 2

        qtbot.wait_until(all_outputs_exist, timeout=5 * 60 * 1000)


class TestFunASRCLI:
    def test_resolves_funasr_api_without_downloading(self, mocker):
        downloader = mocker.patch("buzz.cli.ModelDownloader")

        model_path, model = _resolve_model(
            CommandLineModelType("funasrapi"),
            WhisperModelSize.TINY,
            "",
        )

        assert model_path == ""
        assert model.model_type == ModelType.FUNASR_API
        downloader.assert_not_called()

    def test_funasr_request_does_not_read_openai_token(self, mocker):
        get_password = mocker.patch("buzz.cli.get_password")

        task, initial_prompt, access_token = _normalize_transcription_request(
            model_type=ModelType.FUNASR_API,
            task=Task.TRANSLATE,
            initial_prompt="must be cleared",
            openai_access_token="",
        )

        assert task == Task.TRANSCRIBE
        assert initial_prompt == ""
        assert access_token == ""
        get_password.assert_not_called()
