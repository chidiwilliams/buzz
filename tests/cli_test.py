import os
from tempfile import mkdtemp

import pytest
from pytestqt.qtbot import QtBot

from buzz.cli import parse_command_line
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
