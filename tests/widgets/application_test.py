from unittest.mock import Mock, patch

from buzz.widgets.application import _build_main_window


def test_build_main_window_composes_both_services_with_same_database() -> None:
    database = object()
    transcription_dao = object()
    transcription_segment_dao = object()
    transcription_service = object()
    meeting_repository = object()
    meeting_service = object()
    storage_repository = object()
    meeting_storage = object()
    transcription_repository = object()
    final_reader = object()
    speaker_repository = object()
    speaker_service = object()
    detail_service = object()
    preview_factory = object()
    main_window = Mock(name="main_window")

    with (
        patch(
            "buzz.widgets.application.TranscriptionDAO",
            return_value=transcription_dao,
        ) as transcription_dao_type,
        patch(
            "buzz.widgets.application.TranscriptionSegmentDAO",
            return_value=transcription_segment_dao,
        ) as transcription_segment_dao_type,
        patch(
            "buzz.widgets.application.TranscriptionService",
            return_value=transcription_service,
        ) as transcription_service_type,
        patch(
            "buzz.widgets.application.QSqlMeetingLibraryRepository",
            return_value=meeting_repository,
        ) as meeting_repository_type,
        patch(
            "buzz.widgets.application.MeetingLibraryService",
            return_value=meeting_service,
        ) as meeting_service_type,
        patch(
            "buzz.widgets.application.QSqlMeetingRepository",
            return_value=storage_repository,
        ) as storage_repository_type,
        patch(
            "buzz.widgets.application.MeetingStorage",
            return_value=meeting_storage,
        ) as meeting_storage_type,
        patch(
            "buzz.widgets.application.QSqlMeetingTranscriptionRepository",
            return_value=transcription_repository,
        ) as transcription_repository_type,
        patch(
            "buzz.widgets.application.FinalTranscriptionReadService",
            return_value=final_reader,
        ) as final_reader_type,
        patch(
            "buzz.widgets.application.QSqlMeetingSpeakerRepository",
            return_value=speaker_repository,
        ) as speaker_repository_type,
        patch(
            "buzz.widgets.application.MeetingSpeakerReviewService",
            return_value=speaker_service,
        ) as speaker_service_type,
        patch(
            "buzz.widgets.application.MeetingDetailService",
            return_value=detail_service,
        ) as detail_service_type,
        patch("buzz.widgets.application.AudioPlayer", new=preview_factory),
        patch("buzz.widgets.application.MeetingWorkflow") as workflow_type,
        patch("buzz.widgets.application.MeetingModeController") as controller_type,
        patch("buzz.widgets.application.MeetingTrackTranscriber") as adapter_type,
        patch("buzz.widgets.application.MeetingFinalTranscription") as final_type,
        patch("buzz.widgets.application.QSqlMeetingSummaryRepository") as notes_repo,
        patch("buzz.widgets.application.MeetingNotesService") as notes_service,
        patch("buzz.widgets.application.MeetingNotesController") as notes_controller,
        patch(
            "buzz.widgets.application.MainWindow", return_value=main_window
        ) as main_window_type,
    ):
        result = _build_main_window(database)

    transcription_dao_type.assert_called_once_with(database)
    transcription_segment_dao_type.assert_called_once_with(database)
    transcription_service_type.assert_called_once_with(
        transcription_dao, transcription_segment_dao
    )
    meeting_repository_type.assert_called_once_with(database)
    meeting_service_type.assert_called_once_with(meeting_repository)
    storage_repository_type.assert_called_once_with(database)
    meeting_storage_type.assert_called_once_with(storage_repository)
    transcription_repository_type.assert_called_once_with(database)
    final_reader_type.assert_called_once_with(transcription_repository)
    speaker_repository_type.assert_called_once_with(database)
    speaker_service_type.assert_called_once_with(speaker_repository, final_reader)
    detail_service_type.assert_called_once_with(
        meeting_storage, final_reader, speaker_service
    )
    main_window_type.assert_called_once_with(
        transcription_service,
        meeting_service,
        detail_service,
        speaker_service,
        preview_factory,
        controller_type.return_value,
        final_type.return_value,
        notes_controller.return_value,
    )
    notes_repo.assert_called_once_with(database)
    notes_service.assert_called_once_with(detail_service, notes_repo.return_value)
    notes_controller.assert_called_once_with(notes_service.return_value)
    workflow_type.assert_called_once_with(meeting_storage)
    controller_type.assert_called_once_with(workflow_type.return_value)
    final_type.assert_called_once_with(
        meeting_storage, transcription_repository, adapter_type.return_value
    )
    final_type.return_value.recover.assert_called_once_with()
    assert result is main_window
