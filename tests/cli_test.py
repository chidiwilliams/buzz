import os
import sys
from tempfile import mkdtemp

import pytest
from pytestqt.qtbot import QtBot

from buzz.cli import parse_command_line
from tests.audio import test_audio_path


class TestCLI:
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
                    "small",
                    "--output-directory",
                    mkdtemp(),
                    "--txt",
                    test_audio_path,
                ],
            )
        ],
        indirect=True,
    )
    def test_cli(self, qapp, qapp_args, qtbot: QtBot):
        output_directory = qapp_args[7]

        parse_command_line(qapp)

        def output_exists_at_output_directory():
            assert any(file.endswith(".txt") for file in os.listdir(output_directory))

        qtbot.wait_until(output_exists_at_output_directory, timeout=5 * 60 * 1000)
