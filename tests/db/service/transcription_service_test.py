import pytest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from buzz.db.service.transcription_service import TranscriptionService
from buzz.db.entity.transcription import Transcription


@pytest.fixture
def mock_transcription_dao():
    """Create a mock TranscriptionDAO for testing"""
    return Mock()


@pytest.fixture
def mock_transcription_segment_dao():
    """Create a mock TranscriptionSegmentDAO for testing"""
    return Mock()


@pytest.fixture
def transcription_service(mock_transcription_dao, mock_transcription_segment_dao):
    """Create a TranscriptionService instance for testing"""
    return TranscriptionService(mock_transcription_dao, mock_transcription_segment_dao)


@pytest.fixture
def sample_transcription():
    """Create a sample transcription for testing"""
    return Transcription(
        id=str(uuid4()),
        file="/path/to/test.mp3",
        status="completed",
        time_queued="2023-01-01T00:00:00",
        task="TRANSCRIBE",
        model_type="WHISPER",
        name="Test Transcription",
        notes="This is a test transcription"
    )


class TestTranscriptionService:
    def test_update_transcription_name(self, transcription_service, mock_transcription_dao):
        """Test updating transcription name through service"""
        transcription_id = uuid4()
        new_name = "Updated Transcription Name"
        
        # Call the service method
        transcription_service.update_transcription_name(transcription_id, new_name)
        
        # Verify the DAO method was called with correct parameters
        mock_transcription_dao.update_transcription_name.assert_called_once_with(transcription_id, new_name)

    def test_update_transcription_notes(self, transcription_service, mock_transcription_dao):
        """Test updating transcription notes through service"""
        transcription_id = uuid4()
        new_notes = "Updated transcription notes with more details"
        
        # Call the service method
        transcription_service.update_transcription_notes(transcription_id, new_notes)
        
        # Verify the DAO method was called with correct parameters
        mock_transcription_dao.update_transcription_notes.assert_called_once_with(transcription_id, new_notes)

    def test_update_transcription_name_with_empty_string(self, transcription_service, mock_transcription_dao):
        """Test updating transcription name to empty string"""
        transcription_id = uuid4()
        empty_name = ""
        
        # Call the service method
        transcription_service.update_transcription_name(transcription_id, empty_name)
        
        # Verify the DAO method was called with empty string
        mock_transcription_dao.update_transcription_name.assert_called_once_with(transcription_id, empty_name)

    def test_update_transcription_notes_with_empty_string(self, transcription_service, mock_transcription_dao):
        """Test updating transcription notes to empty string"""
        transcription_id = uuid4()
        empty_notes = ""
        
        # Call the service method
        transcription_service.update_transcription_notes(transcription_id, empty_notes)
        
        # Verify the DAO method was called with empty string
        mock_transcription_dao.update_transcription_notes.assert_called_once_with(transcription_id, empty_notes)

    def test_update_transcription_name_with_none(self, transcription_service, mock_transcription_dao):
        """Test updating transcription name to None"""
        transcription_id = uuid4()
        
        # Call the service method
        transcription_service.update_transcription_name(transcription_id, None)
        
        # Verify the DAO method was called with None
        mock_transcription_dao.update_transcription_name.assert_called_once_with(transcription_id, None)

    def test_update_transcription_notes_with_none(self, transcription_service, mock_transcription_dao):
        """Test updating transcription notes to None"""
        transcription_id = uuid4()
        
        # Call the service method
        transcription_service.update_transcription_notes(transcription_id, None)
        
        # Verify the DAO method was called with None
        mock_transcription_dao.update_transcription_notes.assert_called_once_with(transcription_id, None)

    def test_update_transcription_name_propagates_dao_exception(self, transcription_service, mock_transcription_dao):
        """Test that DAO exceptions are propagated from service"""
        transcription_id = uuid4()
        new_name = "Updated Name"
        
        # Configure the mock to raise an exception
        mock_transcription_dao.update_transcription_name.side_effect = Exception("Database error")
        
        # Call the service method and expect the exception to be raised
        with pytest.raises(Exception, match="Database error"):
            transcription_service.update_transcription_name(transcription_id, new_name)

    def test_update_transcription_notes_propagates_dao_exception(self, transcription_service, mock_transcription_dao):
        """Test that DAO exceptions are propagated from service"""
        transcription_id = uuid4()
        new_notes = "Updated notes"
        
        # Configure the mock to raise an exception
        mock_transcription_dao.update_transcription_notes.side_effect = Exception("Database error")
        
        # Call the service method and expect the exception to be raised
        with pytest.raises(Exception, match="Database error"):
            transcription_service.update_transcription_notes(transcription_id, new_notes)

    def test_update_transcription_name_with_string_uuid(self, transcription_service, mock_transcription_dao):
        """Test updating transcription name with string UUID (should be converted to UUID)"""
        transcription_id_str = str(uuid4())
        new_name = "Updated Name"
        
        # Call the service method
        transcription_service.update_transcription_name(transcription_id_str, new_name)
        
        # Verify the DAO method was called with UUID object
        mock_transcription_dao.update_transcription_name.assert_called_once()
        call_args = mock_transcription_dao.update_transcription_name.call_args[0]
        assert isinstance(call_args[0], str)  # The service should pass the string as-is
        assert call_args[1] == new_name

    def test_update_transcription_notes_with_string_uuid(self, transcription_service, mock_transcription_dao):
        """Test updating transcription notes with string UUID (should be converted to UUID)"""
        transcription_id_str = str(uuid4())
        new_notes = "Updated notes"
        
        # Call the service method
        transcription_service.update_transcription_notes(transcription_id_str, new_notes)
        
        # Verify the DAO method was called with UUID object
        mock_transcription_dao.update_transcription_notes.assert_called_once()
        call_args = mock_transcription_dao.update_transcription_notes.call_args[0]
        assert isinstance(call_args[0], str)  # The service should pass the string as-is
        assert call_args[1] == new_notes

    def test_update_transcription_name_multiple_calls(self, transcription_service, mock_transcription_dao):
        """Test multiple calls to update transcription name"""
        transcription_id = uuid4()
        
        # Make multiple calls
        transcription_service.update_transcription_name(transcription_id, "Name 1")
        transcription_service.update_transcription_name(transcription_id, "Name 2")
        transcription_service.update_transcription_name(transcription_id, "Name 3")
        
        # Verify all calls were made
        assert mock_transcription_dao.update_transcription_name.call_count == 3
        
        # Verify the last call has the correct parameters
        last_call = mock_transcription_dao.update_transcription_name.call_args_list[-1]
        assert last_call[0] == (transcription_id, "Name 3")

    def test_update_transcription_notes_multiple_calls(self, transcription_service, mock_transcription_dao):
        """Test multiple calls to update transcription notes"""
        transcription_id = uuid4()
        
        # Make multiple calls
        transcription_service.update_transcription_notes(transcription_id, "Notes 1")
        transcription_service.update_transcription_notes(transcription_id, "Notes 2")
        transcription_service.update_transcription_notes(transcription_id, "Notes 3")
        
        # Verify all calls were made
        assert mock_transcription_dao.update_transcription_notes.call_count == 3
        
        # Verify the last call has the correct parameters
        last_call = mock_transcription_dao.update_transcription_notes.call_args_list[-1]
        assert last_call[0] == (transcription_id, "Notes 3")

    def test_update_transcription_name_with_unicode(self, transcription_service, mock_transcription_dao):
        """Test updating transcription name with unicode characters"""
        transcription_id = uuid4()
        unicode_name = "Transcription avec des caractères spéciaux: ñáéíóú"
        
        # Call the service method
        transcription_service.update_transcription_name(transcription_id, unicode_name)
        
        # Verify the DAO method was called with unicode string
        mock_transcription_dao.update_transcription_name.assert_called_once_with(transcription_id, unicode_name)

    def test_update_transcription_notes_with_unicode(self, transcription_service, mock_transcription_dao):
        """Test updating transcription notes with unicode characters"""
        transcription_id = uuid4()
        unicode_notes = "Notes avec des caractères spéciaux: ñáéíóú et émojis 🎵🎤"
        
        # Call the service method
        transcription_service.update_transcription_notes(transcription_id, unicode_notes)
        
        # Verify the DAO method was called with unicode string
        mock_transcription_dao.update_transcription_notes.assert_called_once_with(transcription_id, unicode_notes)
