import pytest
from uuid import uuid4

from buzz.db.entity.transcription import Transcription


class TestTranscription:
    def test_transcription_creation_with_name_and_notes(self):
        """Test creating a transcription with name and notes fields"""
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Test Transcription Name",
            notes="This is a test transcription with notes"
        )
        
        assert transcription.name == "Test Transcription Name"
        assert transcription.notes == "This is a test transcription with notes"

    def test_transcription_creation_without_name_and_notes(self):
        """Test creating a transcription without name and notes (should be None)"""
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER"
        )
        
        assert transcription.name is None
        assert transcription.notes is None

    def test_transcription_creation_with_empty_name_and_notes(self):
        """Test creating a transcription with empty name and notes"""
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="",
            notes=""
        )
        
        assert transcription.name == ""
        assert transcription.notes == ""

    def test_transcription_name_assignment(self):
        """Test assigning values to name field"""
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER"
        )
        
        # Test assigning a name
        transcription.name = "New Name"
        assert transcription.name == "New Name"
        
        # Test assigning None
        transcription.name = None
        assert transcription.name is None
        
        # Test assigning empty string
        transcription.name = ""
        assert transcription.name == ""

    def test_transcription_notes_assignment(self):
        """Test assigning values to notes field"""
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER"
        )
        
        # Test assigning notes
        transcription.notes = "New notes"
        assert transcription.notes == "New notes"
        
        # Test assigning None
        transcription.notes = None
        assert transcription.notes is None
        
        # Test assigning empty string
        transcription.notes = ""
        assert transcription.notes == ""

    def test_transcription_with_unicode_name_and_notes(self):
        """Test creating transcription with unicode characters in name and notes"""
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Transcription avec des caractères spéciaux: ñáéíóú",
            notes="Notes avec des caractères spéciaux: ñáéíóú et émojis 🎵🎤"
        )
        
        assert transcription.name == "Transcription avec des caractères spéciaux: ñáéíóú"
        assert transcription.notes == "Notes avec des caractères spéciaux: ñáéíóú et émojis 🎵🎤"

    def test_transcription_with_long_name_and_notes(self):
        """Test creating transcription with very long name and notes"""
        long_name = "A" * 1000  # 1000 character name
        long_notes = "B" * 5000  # 5000 character notes
        
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name=long_name,
            notes=long_notes
        )
        
        assert transcription.name == long_name
        assert transcription.notes == long_notes
        assert len(transcription.name) == 1000
        assert len(transcription.notes) == 5000

    def test_transcription_name_with_special_characters(self):
        """Test transcription name with special characters"""
        special_name = "Transcription with special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?"
        
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name=special_name
        )
        
        assert transcription.name == special_name

    def test_transcription_notes_with_newlines(self):
        """Test transcription notes with newlines and special formatting"""
        notes_with_newlines = """This is a multi-line note
with newlines and special characters:
- Bullet point 1
- Bullet point 2
- Bullet point 3

And some more text after the empty line."""
        
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            notes=notes_with_newlines
        )
        
        assert transcription.notes == notes_with_newlines
        assert "\n" in transcription.notes

    def test_transcription_equality_with_name_and_notes(self):
        """Test transcription equality when name and notes are included"""
        transcription_id = str(uuid4())
        
        transcription1 = Transcription(
            id=transcription_id,
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Test Name",
            notes="Test Notes"
        )
        
        transcription2 = Transcription(
            id=transcription_id,
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Test Name",
            notes="Test Notes"
        )
        
        # Two transcriptions with same ID should be equal
        assert transcription1 == transcription2

    def test_transcription_inequality_with_different_name_and_notes(self):
        """Test transcription inequality when name and notes are different"""
        transcription_id = str(uuid4())
        
        transcription1 = Transcription(
            id=transcription_id,
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Test Name 1",
            notes="Test Notes 1"
        )
        
        transcription2 = Transcription(
            id=transcription_id,
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Test Name 2",
            notes="Test Notes 2"
        )
        
        # Two transcriptions with different name/notes should not be equal
        assert transcription1 != transcription2

    def test_transcription_id_as_uuid_property(self):
        """Test that id_as_uuid property works with name and notes fields"""
        transcription_id = uuid4()
        
        transcription = Transcription(
            id=str(transcription_id),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Test Name",
            notes="Test Notes"
        )
        
        assert transcription.id_as_uuid == transcription_id
        assert isinstance(transcription.id_as_uuid, type(transcription_id))

    def test_transcription_string_representation_with_name_and_notes(self):
        """Test string representation of transcription includes name and notes"""
        transcription = Transcription(
            id="test-id-123",
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Test Transcription",
            notes="Test notes"
        )
        
        str_repr = str(transcription)
        # The string representation should include the ID
        assert "test-id-123" in str_repr

    def test_transcription_with_none_values_in_other_fields(self):
        """Test transcription with None values in other fields but valid name and notes"""
        transcription = Transcription(
            id=str(uuid4()),
            file=None,
            url=None,
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER",
            name="Valid Name",
            notes="Valid Notes"
        )
        
        assert transcription.name == "Valid Name"
        assert transcription.notes == "Valid Notes"
        assert transcription.file is None
        assert transcription.url is None
