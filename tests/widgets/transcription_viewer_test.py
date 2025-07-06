import uuid
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from buzz.locale import _
from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.model_loader import ModelType, WhisperModelSize
from buzz.transcriber.transcriber import Task
from buzz.widgets.transcription_viewer.transcription_view_mode_tool_button import (
    TranscriptionViewModeToolButton,
    ViewMode
)
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)
from buzz.widgets.transcription_viewer.transcription_resizer_widget import (
    TranscriptionResizerWidget,
    TranscriptionWorker,
)
from tests.audio import test_audio_path


class TestTranscriptionViewerWidget:
    @pytest.fixture()
    def transcription(
        self, transcription_dao, transcription_segment_dao
    ) -> Transcription:
        id = uuid.uuid4()
        transcription_dao.insert(
            Transcription(
                id=str(id),
                status="completed",
                file=test_audio_path,
                task=Task.TRANSCRIBE.value,
                model_type=ModelType.WHISPER.value,
                whisper_model_size=WhisperModelSize.SMALL.value,
            )
        )
        transcription_segment_dao.insert(TranscriptionSegment(40, 299, "Bien", "", str(id)))
        transcription_segment_dao.insert(
            TranscriptionSegment(299, 329, "venue dans", "", str(id))
        )

        return transcription_dao.find_by_id(str(id))

    def test_should_display_segments(
        self, qtbot: QtBot, transcription, transcription_service, shortcuts
    ):
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        assert widget.windowTitle() == "whisper-french.mp3"

        editor = widget.findChild(TranscriptionSegmentsEditorWidget)
        assert isinstance(editor, TranscriptionSegmentsEditorWidget)

        assert editor.model().index(0, 1).data() == 299
        assert editor.model().index(0, 2).data() == 40
        assert editor.model().index(0, 3).data() == "Bien"
        widget.close()

    def test_should_update_segment_text(
        self, qtbot, transcription, transcription_service, shortcuts
    ):
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        editor = widget.findChild(TranscriptionSegmentsEditorWidget)
        assert isinstance(editor, TranscriptionSegmentsEditorWidget)

        editor.model().setData(editor.model().index(0, 3), "Biens")
        widget.close()

    def test_should_resize_segment_text(self, qtbot, transcription, transcription_service):
        transcription_service.update_transcription_as_completed = MagicMock()

        widget = TranscriptionResizerWidget(transcription, transcription_service)
        widget.target_chars_spin_box.setValue(5)

        qtbot.add_widget(widget)

        widget.on_resize_button_clicked()

        transcription_service.update_transcription_as_completed.assert_called_once()

        widget.close()

    def test_on_merge_button_clicked(self, qtbot: QtBot, transcription, transcription_service):
        # Prerequisite: Merge button is only enabled if word_level_timings is True
        transcription.word_level_timings = True

        # Mock services and signals
        transcription_service.copy_transcription = MagicMock(return_value=uuid.uuid4())
        transcription_service.update_transcription_progress = MagicMock()

        mock_signal = MagicMock()

        widget = TranscriptionResizerWidget(
            transcription=transcription,
            transcription_service=transcription_service,
            transcriptions_updated_signal=mock_signal)
        qtbot.add_widget(widget)

        # Patch the worker and thread to prevent actual background processing
        with patch('buzz.widgets.transcription_viewer.transcription_resizer_widget.QThread') as mock_thread_class, \
                patch(
                    'buzz.widgets.transcription_viewer.transcription_resizer_widget.TranscriptionWorker') as mock_worker_class:
            mock_worker_instance = MagicMock()
            mock_worker_class.return_value = mock_worker_instance

            mock_thread_instance = MagicMock()
            mock_thread_class.return_value = mock_thread_instance

            # Action: click the merge button
            widget.merge_button.click()

            # Assertions
            # 1. A new transcription is copied
            transcription_service.copy_transcription.assert_called_once_with(transcription.id_as_uuid)
            new_transcript_id = transcription_service.copy_transcription.return_value

            # 2. Progress is updated for the new transcription
            transcription_service.update_transcription_progress.assert_called_once_with(new_transcript_id, 0.0)

            # 3. Signal is emitted to notify of the new transcription
            mock_signal.emit.assert_called_once_with(new_transcript_id)

            # 4. The regroup string is constructed.
            expected_regroup_string_with_bug = 'mg=0.2++42+1_sp=.* /./. /。/?/? /？/!/! /！/,/, _sl=42'

            # 5. Worker is created with the correct arguments
            mock_worker_class.assert_called_once()
            called_args, _ = mock_worker_class.call_args
            assert called_args[0] == transcription
            assert called_args[2] == transcription_service
            assert called_args[3] == expected_regroup_string_with_bug

            # 6. Worker is moved to a new thread and the thread is started
            mock_worker_instance.moveToThread.assert_called_once_with(mock_thread_instance)
            mock_thread_instance.start.assert_called_once()

            # 7. Widget is hidden after starting the process
            assert not widget.isVisible()

            widget.close()

    def test_text_button_changes_view_mode(
            self, qtbot, transcription, transcription_service, shortcuts
    ):
        widget = TranscriptionViewerWidget(
            transcription, transcription_service, shortcuts
        )
        qtbot.add_widget(widget)

        view_mode_tool_button = widget.findChild(TranscriptionViewModeToolButton)
        menu = view_mode_tool_button.menu()

        text_action = next(action for action in menu.actions() if action.text() == _("Text"))
        text_action.trigger()
        assert widget.view_mode == ViewMode.TEXT

        text_action = next(action for action in menu.actions() if action.text() == _("Translation"))
        text_action.trigger()
        assert widget.view_mode == ViewMode.TRANSLATION

        widget.close()

    def test_transcription_worker_calls_stable_whisper(self, qtbot: QtBot, transcription, transcription_service):
        mock_transcription_options = MagicMock()
        mock_transcription_options.extract_speech = False
        regroup_string = "mg=0.2"

        worker = TranscriptionWorker(
            transcription=transcription,
            transcription_options=mock_transcription_options,
            transcription_service=transcription_service,
            regroup_string=regroup_string,
        )

        mock_result_segment = MagicMock()
        mock_result_segment.start = 1.0
        mock_result_segment.end = 2.0
        mock_result_segment.text = "Hello"

        mock_result = MagicMock()
        mock_result.segments = [mock_result_segment]

        with patch('buzz.widgets.transcription_viewer.transcription_resizer_widget.stable_whisper.transcribe_any', return_value=mock_result) as mock_transcribe_any, \
             patch('buzz.widgets.transcription_viewer.transcription_resizer_widget.whisper_audio.load_audio') as mock_load_audio:

            result_ready_spy = MagicMock()
            finished_spy = MagicMock()
            worker.result_ready.connect(result_ready_spy)
            worker.finished.connect(finished_spy)

            worker.run()

            mock_load_audio.assert_called_with(transcription.file)
            
            mock_transcribe_any.assert_called_once()
            call_args, call_kwargs = mock_transcribe_any.call_args
            
            assert call_args[0] == worker.get_transcript
            assert call_kwargs['audio'] == mock_load_audio.return_value
            assert call_kwargs['regroup'] == regroup_string
            assert call_kwargs['vad'] is True
            assert call_kwargs['suppress_silence'] is True

            result_ready_spy.assert_called_once()
            emitted_segments = result_ready_spy.call_args[0][0]
            assert len(emitted_segments) == 1
            assert emitted_segments[0].start == 100
            assert emitted_segments[0].end == 200
            assert emitted_segments[0].text == "Hello"
            
            finished_spy.assert_called_once()
