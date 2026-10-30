from unittest.mock import patch, MagicMock, mock_open
import json
import os
import subprocess
import sys

import pytest

from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import (
    TranscriptionOptions,
    Task,
    FileTranscriptionTask,
    FileTranscriptionOptions,
)
from buzz.transcriber import whisper_cpp
from buzz.transcriber.whisper_cpp import WhisperCpp, _is_cli_safe_path
from tests.audio import test_audio_path, test_multibyte_utf8_audio_path
from tests.model_loader import get_model_path


def _whisper_env_source() -> dict:
    # On Windows _whisper_env() copies the app_env snapshot, not os.environ
    return whisper_cpp.app_env if sys.platform == "win32" else os.environ


class TestWhisperCpp:
    def test_transcribe(self):
        transcription_options = TranscriptionOptions(
            language="fr",
            task=Task.TRANSCRIBE,
            word_level_timings=False,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )
        model_path = get_model_path(transcription_options.model)

        task = FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path=model_path,
            file_path=test_audio_path,
        )

        segments = WhisperCpp.transcribe(task=task)

        # Combine all segment texts
        full_text = " ".join(segment.text for segment in segments)
        assert "Bien venu" in full_text or "bienvenu" in full_text.lower()

    def test_detect_language(self):
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.TINY,
        )
        model_path = get_model_path(model)

        assert WhisperCpp.detect_language(test_audio_path, model_path) == "fr"
        assert (
            WhisperCpp.detect_language(test_multibyte_utf8_audio_path, model_path)
            == "lv"
        )

    def test_detect_language_parses_stderr(self):
        completed = MagicMock(
            stderr="whisper_full_with_state: auto-detected language: de (p = 0.98)\n",
            stdout="",
        )
        with patch(
            "buzz.transcriber.whisper_cpp.subprocess.run", return_value=completed
        ) as run_mock, patch(
            "buzz.transcriber.whisper_cpp.get_whisper_cli_path",
            return_value="/fake/whisper-cli",
        ):
            result = WhisperCpp.detect_language("/fake/audio.wav", "/fake/model.bin")

        assert result == "de"
        cmd = run_mock.call_args[0][0]
        assert "--detect-language" in cmd
        assert cmd[cmd.index("--model") + 1] == "/fake/model.bin"
        # A supported format is passed straight through, no conversion.
        assert cmd[cmd.index("-f") + 1] == "/fake/audio.wav"

    def test_detect_language_no_match_returns_none(self):
        completed = MagicMock(stderr="no language line here\n", stdout="")
        with patch(
            "buzz.transcriber.whisper_cpp.subprocess.run", return_value=completed
        ), patch(
            "buzz.transcriber.whisper_cpp.get_whisper_cli_path",
            return_value="/fake/whisper-cli",
        ):
            assert (
                WhisperCpp.detect_language("/fake/audio.wav", "/fake/model.bin") is None
            )

    def test_detect_language_converts_unsupported_format(self):
        # .m4a is not directly supported, so ffmpeg should convert to .wav first
        # and the converted path should be fed to whisper-cli.
        detect_result = MagicMock(
            stderr="auto-detected language: en (p = 0.9)\n", stdout=""
        )
        calls = []

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd[0] == "ffmpeg":
                return MagicMock(returncode=0)
            return detect_result

        with patch(
            "buzz.transcriber.whisper_cpp.subprocess.run", side_effect=fake_run
        ), patch(
            "buzz.transcriber.whisper_cpp.get_whisper_cli_path",
            return_value="/fake/whisper-cli",
        ):
            result = WhisperCpp.detect_language("/fake/audio.m4a", "/fake/model.bin")

        assert result == "en"
        assert calls[0][0] == "ffmpeg"
        converted = calls[0][-1]
        assert os.path.basename(converted).isascii()
        assert converted.endswith(".wav")
        detect_cmd = calls[-1]
        assert detect_cmd[detect_cmd.index("-f") + 1] == converted
        # The temp WAV is removed once detection is done.
        assert not os.path.exists(converted)

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("C:\\録音\\会議の録音.mp4", True),
            ("C:\\録音\\鷗外の講演.mp4", False),
            ("C:\\録音\\𠮟る.mp3", False),
            ("C:\\録音\\한국어.mp3", False),
            ("C:\\録音\\Café.mp3", False),
        ],
    )
    def test_is_cli_safe_path_checks_ansi_code_page(self, path, expected):
        assert _is_cli_safe_path(path, encoding="cp932") is expected

    def test_is_cli_safe_path_always_true_off_windows(self):
        with patch("buzz.transcriber.whisper_cpp.sys.platform", "linux"):
            assert _is_cli_safe_path("/tmp/한국어 🎤.mp3") is True

    def test_prepare_input_copies_unsafe_path_to_ascii_temp(self, tmp_path):
        source = tmp_path / "鷗外の講演.mp3"
        source.write_bytes(b"audio bytes")

        with patch(
            "buzz.transcriber.whisper_cpp._is_cli_safe_path", return_value=False
        ):
            file_to_process, temp_file = WhisperCpp._prepare_input(
                str(source), (".mp3", ".wav", ".flac")
            )

        try:
            assert file_to_process == temp_file
            assert os.path.basename(temp_file).isascii()
            assert temp_file.endswith(".mp3")
            with open(temp_file, "rb") as f:
                assert f.read() == b"audio bytes"
        finally:
            os.remove(temp_file)

    def test_prepare_input_passes_safe_path_through(self):
        with patch(
            "buzz.transcriber.whisper_cpp._is_cli_safe_path", return_value=True
        ):
            assert WhisperCpp._prepare_input(
                "/fake/会議の録音.mp3", (".mp3", ".wav", ".flac")
            ) == ("/fake/会議の録音.mp3", None)

    def test_convert_to_wav_removes_temp_file_on_failure(self):
        created = []

        def fake_run(cmd, *args, **kwargs):
            created.append(cmd[-1])
            raise subprocess.CalledProcessError(1, cmd, stderr=b"bad input")

        with patch("buzz.transcriber.whisper_cpp.subprocess.run", side_effect=fake_run):
            with pytest.raises(Exception, match="bad input"):
                WhisperCpp._convert_to_wav("/fake/鷗外の講演.mp4")

        assert created and not os.path.exists(created[0])

    def test_transcribe_unsafe_path_runs_whisper_on_temp_copy(self, tmp_path):
        source = tmp_path / "鷗外の講演.mp3"
        source.write_bytes(b"audio bytes")

        task = FileTranscriptionTask(
            transcription_options=TranscriptionOptions(
                language="ja",
                task=Task.TRANSCRIBE,
                word_level_timings=False,
                model=TranscriptionModel(
                    model_type=ModelType.WHISPER_CPP,
                    whisper_model_size=WhisperModelSize.TINY,
                ),
            ),
            file_transcription_options=FileTranscriptionOptions(),
            model_path="/fake/model.bin",
            file_path=str(source),
        )

        cmds = []

        def fake_run_whisper(cmd):
            cmds.append(cmd)
            file_to_process = cmd[cmd.index("-f") + 1]
            with open(f"{file_to_process}.json", "w") as f:
                json.dump({"transcription": [
                    {"offsets": {"from": 0, "to": 1000}, "text": "こんにちは"}
                ]}, f)
            return 0, ""

        with patch(
            "buzz.transcriber.whisper_cpp._is_cli_safe_path", return_value=False
        ), patch.object(WhisperCpp, "_run_whisper", side_effect=fake_run_whisper):
            segments = WhisperCpp.transcribe(task)

        assert len(segments) == 1
        file_to_process = cmds[0][cmds[0].index("-f") + 1]
        assert file_to_process != str(source)
        assert os.path.basename(file_to_process).isascii()
        # Temp copy and its JSON output are cleaned up; the source is untouched.
        assert not os.path.exists(file_to_process)
        assert not os.path.exists(f"{file_to_process}.json")
        assert source.exists()

    def test_transcribe_word_level_timestamps(self):
        transcription_options = TranscriptionOptions(
            language="lv",
            task=Task.TRANSCRIBE,
            word_level_timings=True,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )
        model_path = get_model_path(transcription_options.model)

        task = FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path=model_path,
            file_path=test_multibyte_utf8_audio_path,
        )

        segments = WhisperCpp.transcribe(task=task)

        assert "Mani" in segments[0].text
        assert "uzstrau" or "ustrau" in segments[1].text
        assert "laikabstāk" in segments[2].text

    def test_transcribe_chinese_multibyte_word_level_timestamps(self):
        """Test that Chinese characters split across multiple tokens are properly combined.

        Chinese character 闻 (U+95FB) is encoded as UTF-8 bytes E9 97 BB.
        Whisper.cpp may split this into separate tokens, e.g.:
        - Token 1: bytes E9 97 (incomplete)
        - Token 2: byte BB (completes the character)

        The code should combine these bytes and output 闻 as a single segment.
        """
        # Mock JSON data simulating whisper.cpp output with split Chinese characters
        # The character 闻 is split into two tokens: \xe9\x97 and \xbb
        # The character 新 is a complete token
        # Together they form 新闻 (news)
        mock_json_data = {
            "transcription": [
                {
                    # Segment offsets span the same range as the tokens below;
                    # whisper.cpp emits them this way so VAD offset remapping is a no-op here.
                    "offsets": {"from": 100, "to": 400},
                    "text": "",  # Not used in word-level processing
                    "tokens": [
                        {
                            "text": "[_BEG_]",
                            "offsets": {"from": 0, "to": 0},
                        },
                        {
                            # 新 - complete character (UTF-8: E6 96 B0)
                            # When read as latin-1: \xe6\x96\xb0
                            "text": "\xe6\x96\xb0",
                            "offsets": {"from": 100, "to": 200},
                        },
                        {
                            # First two bytes of 闻 (UTF-8: E9 97 BB)
                            # When read as latin-1: \xe9\x97
                            "text": "\xe9\x97",
                            "offsets": {"from": 200, "to": 300},
                        },
                        {
                            # Last byte of 闻
                            # When read as latin-1: \xbb
                            "text": "\xbb",
                            "offsets": {"from": 300, "to": 400},
                        },
                        {
                            "text": "[_TT_500]",
                            "offsets": {"from": 500, "to": 500},
                        },
                    ],
                }
            ]
        }

        # Convert to JSON string using latin-1 compatible encoding
        # We write bytes directly since the real file is read with latin-1
        json_bytes = json.dumps(mock_json_data, ensure_ascii=False).encode("latin-1")

        transcription_options = TranscriptionOptions(
            language="zh",
            task=Task.TRANSCRIBE,
            word_level_timings=True,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )

        task = FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="/fake/model/path",
            file_path="/fake/audio.wav",
        )

        # Mock subprocess.Popen to simulate whisper-cli execution
        mock_process = MagicMock()
        mock_process.stderr.readline.side_effect = [""]
        mock_process.wait.return_value = None
        mock_process.returncode = 0

        with patch("buzz.transcriber.whisper_cpp.subprocess.Popen", return_value=mock_process):
            with patch("buzz.transcriber.whisper_cpp.os.path.exists", return_value=True):
                with patch("builtins.open", mock_open(read_data=json_bytes.decode("latin-1"))):
                    segments = WhisperCpp.transcribe(task=task)

        # Should have 2 segments: 新 and 闻 (each character separate)
        assert len(segments) == 2
        assert segments[0].text == "新"
        assert segments[1].text == "闻"

        # Verify timestamps
        assert segments[0].start == 100
        assert segments[0].end == 200
        # 闻 spans from token at 200 to token ending at 400
        assert segments[1].start == 200
        assert segments[1].end == 400

    def test_transcribe_chinese_mixed_complete_and_split_chars(self):
        """Test a mix of complete and split Chinese characters."""
        # 大家好 - "Hello everyone"
        # 大 (E5 A4 A7) - complete token
        # 家 (E5 AE B6) - split into E5 AE and B6
        # 好 (E5 A5 BD) - complete token
        mock_json_data = {
            "transcription": [
                {
                    # Segment offsets span the same range as the tokens below;
                    # whisper.cpp emits them this way so VAD offset remapping is a no-op here.
                    "offsets": {"from": 100, "to": 400},
                    "text": "",  # Not used in word-level processing
                    "tokens": [
                        {
                            "text": "[_BEG_]",
                            "offsets": {"from": 0, "to": 0},
                        },
                        {
                            # 大 - complete
                            "text": "\xe5\xa4\xa7",
                            "offsets": {"from": 100, "to": 200},
                        },
                        {
                            # First two bytes of 家
                            "text": "\xe5\xae",
                            "offsets": {"from": 200, "to": 250},
                        },
                        {
                            # Last byte of 家
                            "text": "\xb6",
                            "offsets": {"from": 250, "to": 300},
                        },
                        {
                            # 好 - complete
                            "text": "\xe5\xa5\xbd",
                            "offsets": {"from": 300, "to": 400},
                        },
                    ],
                }
            ]
        }

        json_bytes = json.dumps(mock_json_data, ensure_ascii=False).encode("latin-1")

        transcription_options = TranscriptionOptions(
            language="zh",
            task=Task.TRANSCRIBE,
            word_level_timings=True,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )

        task = FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="/fake/model/path",
            file_path="/fake/audio.wav",
        )

        mock_process = MagicMock()
        mock_process.stderr.readline.side_effect = [""]
        mock_process.wait.return_value = None
        mock_process.returncode = 0

        with patch("buzz.transcriber.whisper_cpp.subprocess.Popen", return_value=mock_process):
            with patch("buzz.transcriber.whisper_cpp.os.path.exists", return_value=True):
                with patch("builtins.open", mock_open(read_data=json_bytes.decode("latin-1"))):
                    segments = WhisperCpp.transcribe(task=task)

        # Should have 3 segments: 大, 家, 好
        assert len(segments) == 3
        assert segments[0].text == "大"
        assert segments[1].text == "家"
        assert segments[2].text == "好"

        # Combined text
        full_text = "".join(s.text for s in segments)
        assert full_text == "大家好"

    @staticmethod
    def _run_with_mocked_json(mock_json_data, language, vad_enabled):
        """Run WhisperCpp.transcribe against mocked whisper-cli JSON output.

        os.path.exists drives whether the VAD model is considered available, which
        in turn enables the per-token offset remapping.
        """
        json_bytes = json.dumps(mock_json_data, ensure_ascii=False).encode("latin-1")

        transcription_options = TranscriptionOptions(
            language=language,
            task=Task.TRANSCRIBE,
            word_level_timings=True,
            model=TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=WhisperModelSize.TINY,
            ),
        )

        task = FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=FileTranscriptionOptions(),
            model_path="/fake/model/path",
            file_path="/fake/audio.wav",
        )

        mock_process = MagicMock()
        mock_process.stderr.readline.side_effect = [""]
        mock_process.wait.return_value = None
        mock_process.returncode = 0

        with patch("buzz.transcriber.whisper_cpp.subprocess.Popen", return_value=mock_process):
            with patch("buzz.transcriber.whisper_cpp.os.path.exists", return_value=vad_enabled):
                with patch("builtins.open", mock_open(read_data=json_bytes.decode("latin-1"))):
                    return WhisperCpp.transcribe(task=task)

    def test_vad_remaps_word_offsets_to_original_time(self):
        """With VAD enabled, whisper-cli remaps segment offsets back to the original
        audio timeline but leaves per-token offsets in the VAD-compressed timeline.

        Word-level timestamps must be rescaled onto the segment's original time range
        so leading silence does not push every word toward 0.
        """
        # Segment plays at 15.0s-21.0s in the original audio (silence trimmed by VAD),
        # but its tokens are reported in compressed time spanning 0-3000ms.
        # scale = (21000 - 15000) / (3000 - 0) = 2.0
        mock_json_data = {
            "transcription": [
                {
                    "offsets": {"from": 15000, "to": 21000},
                    "text": "",
                    "tokens": [
                        {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}},
                        {"text": " Hello", "offsets": {"from": 0, "to": 1000}},
                        {"text": " world", "offsets": {"from": 1500, "to": 3000}},
                    ],
                }
            ]
        }

        segments = self._run_with_mocked_json(mock_json_data, language="en", vad_enabled=True)

        assert len(segments) == 2
        assert segments[0].text == "Hello"
        assert segments[1].text == "world"

        # Remapped onto the segment's original 15000-21000ms range, not near 0.
        assert segments[0].start == 15000
        assert segments[0].end == 17000
        assert segments[1].start == 18000
        assert segments[1].end == 21000

    def test_word_offsets_unchanged_without_vad(self):
        """Without VAD, token offsets are already in original time and must pass
        through the remapper unchanged (identity)."""
        mock_json_data = {
            "transcription": [
                {
                    "offsets": {"from": 0, "to": 3000},
                    "text": "",
                    "tokens": [
                        {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}},
                        {"text": " Hello", "offsets": {"from": 0, "to": 1000}},
                        {"text": " world", "offsets": {"from": 1500, "to": 3000}},
                    ],
                }
            ]
        }

        segments = self._run_with_mocked_json(mock_json_data, language="en", vad_enabled=False)

        assert len(segments) == 2
        assert segments[0].text == "Hello"
        assert segments[0].start == 0
        assert segments[0].end == 1000
        assert segments[1].text == "world"
        assert segments[1].start == 1500
        assert segments[1].end == 3000

    def test_parse_segment_timings_handles_truncated_utf8_without_mojibake(self):
        """When whisper-cli produces text ending in an incomplete UTF-8 byte sequence,
        it should not fall back to Latin-1 mojibake."""
        # 'Bieži vien' encoded as UTF-8 bytes then read as latin-1, plus a lone \xc4 byte at the end
        utf8_bytes = "Bieži vien".encode("utf-8") + b"\xc4"
        latin1_text = utf8_bytes.decode("latin-1")

        mock_result = {
            "transcription": [
                {
                    "offsets": {"from": 0, "to": 5000},
                    "text": latin1_text,
                }
            ]
        }
        segments = WhisperCpp._parse_segment_timings(mock_result)
        assert len(segments) == 1
        assert segments[0].text == "Bieži vien"

    def test_parse_segment_timings_filters_aborted_superseded_fragments(self):
        """When whisper chunk boundary emits an aborted stub (e.g. 100ms) with start time
        matching the next segment, the aborted fragment must be filtered out."""
        mock_result = {
            "transcription": [
                {
                    "offsets": {"from": 2180, "to": 16180},
                    "text": "First complete sentence.".encode("utf-8").decode("latin-1"),
                },
                {
                    # Aborted 100ms fragment superseded by the next chunk starting at 16180
                    "offsets": {"from": 16180, "to": 16280},
                    "text": "Second sentence partial".encode("utf-8").decode("latin-1"),
                },
                {
                    # Full re-transcription of the second sentence
                    "offsets": {"from": 16180, "to": 34960},
                    "text": "Second sentence complete and long.".encode("utf-8").decode("latin-1"),
                },
                {
                    "offsets": {"from": 34960, "to": 36700},
                    "text": "Third sentence.".encode("utf-8").decode("latin-1"),
                },
            ]
        }
        segments = WhisperCpp._parse_segment_timings(mock_result)
        assert len(segments) == 3
        assert segments[0].start == 2180
        assert segments[0].end == 16180
        assert segments[0].text == "First complete sentence."

        assert segments[1].start == 16180
        assert segments[1].end == 34960
        assert segments[1].text == "Second sentence complete and long."

        assert segments[2].start == 34960
        assert segments[2].end == 36700
        assert segments[2].text == "Third sentence."

    def test_parse_word_level_timings_filters_aborted_superseded_fragments(self):
        """Word-level timings should also filter out aborted segment blocks."""
        mock_result = {
            "transcription": [
                {
                    "offsets": {"from": 0, "to": 2000},
                    "text": "",
                    "tokens": [
                        {"text": " Hello", "offsets": {"from": 0, "to": 1000}},
                        {"text": " world", "offsets": {"from": 1000, "to": 2000}},
                    ],
                },
                {
                    # Aborted fragment starting at 2000
                    "offsets": {"from": 2000, "to": 2100},
                    "text": "",
                    "tokens": [
                        {"text": " Good", "offsets": {"from": 2000, "to": 2050}},
                    ],
                },
                {
                    # Re-transcribed block starting at 2000
                    "offsets": {"from": 2000, "to": 4000},
                    "text": "",
                    "tokens": [
                        {"text": " Goodbye", "offsets": {"from": 2000, "to": 3000}},
                        {"text": " all", "offsets": {"from": 3000, "to": 4000}},
                    ],
                },
            ]
        }
        segments = WhisperCpp._parse_word_level_timings(mock_result, language="en", vad_enabled=False)
        words = [s.text for s in segments]
        assert words == ["Hello", "world", "Goodbye", "all"]

    def test_whisper_env_selects_discrete_gpu(self, monkeypatch):
        monkeypatch.delitem(_whisper_env_source(), "GGML_VK_VISIBLE_DEVICES", raising=False)
        with patch("buzz.transcriber.whisper_cpp.DISCRETE_GPU_INDEX", 1):
            assert WhisperCpp._whisper_env()["GGML_VK_VISIBLE_DEVICES"] == "1"

    def test_whisper_env_keeps_user_device_choice(self, monkeypatch):
        monkeypatch.setitem(_whisper_env_source(), "GGML_VK_VISIBLE_DEVICES", "0")
        with patch("buzz.transcriber.whisper_cpp.DISCRETE_GPU_INDEX", 1):
            assert WhisperCpp._whisper_env()["GGML_VK_VISIBLE_DEVICES"] == "0"

    def test_detect_language_uses_discrete_gpu(self, monkeypatch):
        monkeypatch.delitem(_whisper_env_source(), "GGML_VK_VISIBLE_DEVICES", raising=False)
        completed = MagicMock(stderr="auto-detected language: en (p = 0.9)\n", stdout="")
        with patch(
            "buzz.transcriber.whisper_cpp.subprocess.run", return_value=completed
        ) as run_mock, patch(
            "buzz.transcriber.whisper_cpp.get_whisper_cli_path",
            return_value="/fake/whisper-cli",
        ), patch("buzz.transcriber.whisper_cpp.DISCRETE_GPU_INDEX", 1):
            WhisperCpp.detect_language("/fake/audio.wav", "/fake/model.bin")

        assert run_mock.call_args.kwargs["env"]["GGML_VK_VISIBLE_DEVICES"] == "1"

    def test_whisper_env_without_discrete_gpu(self, monkeypatch):
        monkeypatch.delitem(_whisper_env_source(), "GGML_VK_VISIBLE_DEVICES", raising=False)
        with patch("buzz.transcriber.whisper_cpp.DISCRETE_GPU_INDEX", None):
            assert "GGML_VK_VISIBLE_DEVICES" not in WhisperCpp._whisper_env()

    def test_vulkan_instance_uses_loader_api_version(self):
        # ggml-vulkan creates its instance at the loader's highest API version, and the
        # device order can differ between versions, so the probe must use the same one
        vk = MagicMock()
        vk.vkEnumerateInstanceVersion.return_value = 4206592  # 1.3.0

        instance = whisper_cpp._create_vulkan_instance(vk)

        vk.VkApplicationInfo.assert_called_once_with(apiVersion=4206592)
        vk.VkInstanceCreateInfo.assert_called_once_with(
            pApplicationInfo=vk.VkApplicationInfo.return_value
        )
        vk.vkCreateInstance.assert_called_once_with(vk.VkInstanceCreateInfo.return_value, None)
        assert instance is vk.vkCreateInstance.return_value

    @staticmethod
    def _fake_vulkan(device_types):
        vk = MagicMock()
        vk.VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU = 1
        vk.VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU = 2
        vk.VK_PHYSICAL_DEVICE_TYPE_CPU = 4
        devices = [MagicMock(deviceType=t, deviceName=f"gpu{i}") for i, t in enumerate(device_types)]
        vk.vkEnumeratePhysicalDevices.return_value = list(range(len(devices)))
        vk.vkGetPhysicalDeviceProperties.side_effect = lambda index: devices[index]
        return vk

    def test_find_discrete_gpu_index_after_integrated(self):
        vk = self._fake_vulkan([1, 2, 4])
        assert whisper_cpp._find_discrete_gpu_index(vk, MagicMock()) == 1

    def test_find_discrete_gpu_index_returns_first_discrete(self):
        vk = self._fake_vulkan([2, 1, 2])
        assert whisper_cpp._find_discrete_gpu_index(vk, MagicMock()) == 0

    def test_find_discrete_gpu_index_without_discrete(self):
        vk = self._fake_vulkan([1, 4])
        assert whisper_cpp._find_discrete_gpu_index(vk, MagicMock()) is None
