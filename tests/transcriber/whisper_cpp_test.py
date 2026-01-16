from unittest.mock import patch, MagicMock, mock_open
import json

from buzz.model_loader import TranscriptionModel, ModelType, WhisperModelSize
from buzz.transcriber.transcriber import (
    TranscriptionOptions,
    Task,
    FileTranscriptionTask,
    FileTranscriptionOptions,
)
from buzz.transcriber.whisper_cpp import WhisperCpp
from tests.audio import test_audio_path, test_multibyte_utf8_audio_path
from tests.model_loader import get_model_path


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
        assert "Bien venu" in full_text

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
                    "offsets": {"from": 0, "to": 5000},
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
                    "offsets": {"from": 0, "to": 5000},
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