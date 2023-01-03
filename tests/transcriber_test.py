import logging
import os
import pathlib
import platform
import tempfile
import time
from typing import List
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtCore import QThread, QCoreApplication
from pytestqt.qtbot import QtBot

from buzz.model_loader import WhisperModelSize, ModelType, TranscriptionModel, ModelLoader
from buzz.transcriber import (FileTranscriptionOptions, FileTranscriptionTask, OutputFormat, RecordingTranscriber,
                              Segment, Task, WhisperCpp, WhisperCppFileTranscriber,
                              WhisperFileTranscriber,
                              get_default_output_file_path, to_timestamp,
                              whisper_cpp_params, write_output, TranscriptionOptions)
from tests.mock_sounddevice import MockInputStream
from tests.model_loader import get_model_path


@pytest.mark.skip()
class TestRecordingTranscriber:
    def test_should_transcribe(self, qtbot):
        thread = QThread()

        transcription_model = TranscriptionModel(model_type=ModelType.WHISPER_CPP,
                                                 whisper_model_size=WhisperModelSize.TINY)
        model_loader = ModelLoader(model=transcription_model)
        model_loader.moveToThread(thread)

        transcriber = RecordingTranscriber(transcription_options=TranscriptionOptions(
            model=transcription_model, language='fr', task=Task.TRANSCRIBE),
            input_device_index=0)
        transcriber.moveToThread(thread)

        thread.started.connect(model_loader.run)
        thread.finished.connect(thread.deleteLater)

        model_loader.finished.connect(transcriber.start)
        model_loader.finished.connect(model_loader.deleteLater)

        mock_transcription = Mock()
        transcriber.transcription.connect(mock_transcription)

        transcriber.finished.connect(thread.quit)
        transcriber.finished.connect(transcriber.deleteLater)

        with patch('sounddevice.InputStream', side_effect=MockInputStream), patch(
                'sounddevice.check_input_settings'), qtbot.wait_signal(transcriber.transcription, timeout=60 * 1000):
            thread.start()

        with qtbot.wait_signal(thread.finished, timeout=60 * 1000):
            transcriber.stop_recording()

        text = mock_transcription.call_args[0][0]
        assert 'Bienvenue dans Passe' in text


@pytest.mark.skipif(platform.system() == 'Windows', reason='whisper_cpp not printing segments on Windows')
class TestWhisperCppFileTranscriber:
    @pytest.mark.parametrize(
        'word_level_timings,expected_segments',
        [
            (False, [Segment(0, 1840, 'Bienvenue dans Passe Relle.')]),
            (True, [Segment(30, 280, 'Bien'), Segment(280, 630, 'venue')])
        ])
    def test_transcribe(self, qtbot: QtBot, word_level_timings: bool, expected_segments: List[Segment]):
        file_transcription_options = FileTranscriptionOptions(
            file_paths=['testdata/whisper-french.mp3'])
        transcription_options = TranscriptionOptions(language='fr', task=Task.TRANSCRIBE,
                                                     word_level_timings=word_level_timings,
                                                     model=TranscriptionModel(model_type=ModelType.WHISPER_CPP,
                                                                              whisper_model_size=WhisperModelSize.TINY))

        model_path = get_model_path(transcription_options.model)
        transcriber = WhisperCppFileTranscriber(
            task=FileTranscriptionTask(file_path='testdata/whisper-french.mp3',
                                       transcription_options=transcription_options,
                                       file_transcription_options=file_transcription_options, model_path=model_path))
        mock_progress = Mock()
        mock_completed = Mock()
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.waitSignal(transcriber.completed, timeout=10 * 60 * 1000):
            transcriber.run()

        mock_progress.assert_called()
        segments = mock_completed.call_args[0][0]
        for expected_segment in expected_segments:
            assert expected_segment in segments


class TestWhisperFileTranscriber:
    def test_default_output_file(self):
        srt = get_default_output_file_path(
            Task.TRANSLATE, '/a/b/c.mp4', OutputFormat.TXT)
        assert srt.startswith('/a/b/c (Translated on ')
        assert srt.endswith('.txt')

        srt = get_default_output_file_path(
            Task.TRANSLATE, '/a/b/c.mp4', OutputFormat.SRT)
        assert srt.startswith('/a/b/c (Translated on ')
        assert srt.endswith('.srt')

    @pytest.mark.parametrize(
        'word_level_timings,expected_segments,model,check_progress',
        [
            (False, [Segment(0, 6560,
                             ' Bienvenue dans Passe-Relle. Un podcast pensé pour évêiller la curiosité des apprenances')],
             TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY), True),
            (True, [Segment(40, 299, ' Bien'), Segment(299, 329, 'venue dans')],
             TranscriptionModel(model_type=ModelType.WHISPER, whisper_model_size=WhisperModelSize.TINY), True),
            (False, [Segment(0, 8517,
                             ' Bienvenue dans Passe-Relle. Un podcast pensé pour évêyer la curiosité des apprenances '
                             'et des apprenances de français.')],
             TranscriptionModel(model_type=ModelType.HUGGING_FACE,
                                hugging_face_model_id='openai/whisper-tiny'), False)
        ])
    def test_transcribe(self, qtbot: QtBot, word_level_timings: bool, expected_segments: List[Segment],
                        model: TranscriptionModel, check_progress):
        mock_progress = Mock()
        mock_completed = Mock()
        transcription_options = TranscriptionOptions(language='fr', task=Task.TRANSCRIBE,
                                                     word_level_timings=word_level_timings,
                                                     model=model)
        model_path = get_model_path(transcription_options.model)
        file_transcription_options = FileTranscriptionOptions(
            file_paths=['testdata/whisper-french.mp3'])

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(transcription_options=transcription_options,
                                       file_transcription_options=file_transcription_options,
                                       file_path='testdata/whisper-french.mp3', model_path=model_path))
        transcriber.progress.connect(mock_progress)
        transcriber.completed.connect(mock_completed)
        with qtbot.wait_signal(transcriber.progress, timeout=10 * 6000), qtbot.wait_signal(transcriber.completed,
                                                                                           timeout=10 * 6000):
            transcriber.run()

        if check_progress:
            # Reports progress at 0, 0<progress<100, and 100
            assert any(
                [call_args.args[0] == (0, 100) for call_args in mock_progress.call_args_list])
            assert any(
                [call_args.args[0] == (100, 100) for call_args in mock_progress.call_args_list])
            assert any(
                [(0 < call_args.args[0][0] < 100) and (call_args.args[0][1] == 100) for call_args in
                 mock_progress.call_args_list])

        mock_completed.assert_called()
        segments = mock_completed.call_args[0][0]
        assert len(segments) >= len(expected_segments)
        for (i, expected_segment) in enumerate(expected_segments):
            assert segments[i] == expected_segment

    @pytest.mark.skip()
    def test_transcribe_stop(self):
        output_file_path = os.path.join(tempfile.gettempdir(), 'whisper.txt')
        if os.path.exists(output_file_path):
            os.remove(output_file_path)

        file_transcription_options = FileTranscriptionOptions(
            file_paths=['testdata/whisper-french.mp3'])
        transcription_options = TranscriptionOptions(
            language='fr', task=Task.TRANSCRIBE, word_level_timings=False,
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY))
        model_path = get_model_path(transcription_options.model)

        transcriber = WhisperFileTranscriber(
            task=FileTranscriptionTask(model_path=model_path, transcription_options=transcription_options,
                                       file_transcription_options=file_transcription_options,
                                       file_path='testdata/whisper-french.mp3'))
        transcriber.run()
        time.sleep(1)
        transcriber.stop()

        # Assert that file was not created
        assert os.path.isfile(output_file_path) is False


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == '00:00:00.000'
        assert to_timestamp(123456789) == '34:17:36.789'


class TestWhisperCpp:
    def test_transcribe(self):
        transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.WHISPER_CPP, whisper_model_size=WhisperModelSize.TINY))
        model_path = get_model_path(transcription_options.model)

        whisper_cpp = WhisperCpp(model=model_path)
        params = whisper_cpp_params(
            language='fr', task=Task.TRANSCRIBE, word_level_timings=False)
        result = whisper_cpp.transcribe(
            audio='testdata/whisper-french.mp3', params=params)

        assert 'Bienvenue dans Passe' in result['text']


@pytest.mark.parametrize(
    'output_format,output_text',
    [
        (OutputFormat.TXT, 'Bien venue dans\n'),
        (
                OutputFormat.SRT,
                '1\n00:00:00,040 --> 00:00:00,299\nBien\n\n2\n00:00:00,299 --> 00:00:00,329\nvenue dans\n\n'),
        (OutputFormat.VTT,
         'WEBVTT\n\n00:00:00.040 --> 00:00:00.299\nBien\n\n00:00:00.299 --> 00:00:00.329\nvenue dans\n\n'),
    ])
def test_write_output(tmp_path: pathlib.Path, output_format: OutputFormat, output_text: str):
    output_file_path = tmp_path / 'whisper.txt'
    segments = [Segment(40, 299, 'Bien'), Segment(299, 329, 'venue dans')]

    write_output(path=str(output_file_path), segments=segments,
                 should_open=False, output_format=output_format)

    output_file = open(output_file_path, 'r', encoding='utf-8')
    assert output_text == output_file.read()
