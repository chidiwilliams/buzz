import pytest
from unittest.mock import Mock, patch
from uuid import UUID, uuid4
from PyQt6.QtSql import QSqlQuery

from buzz.db.entity.transcription import Transcription


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


class TestTranscriptionDAO:
    def test_insert_transcription_with_name_and_notes(self, transcription_dao, sample_transcription):
        """Test inserting a transcription with name and notes fields"""
        transcription_dao.insert(sample_transcription)
        
        # Verify the transcription was inserted
        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT * FROM transcription WHERE id = :id")
        query.bindValue(":id", sample_transcription.id)
        assert query.exec()
        assert query.next()
        
        # Check that name and notes were stored
        assert query.value("name") == "Test Transcription"
        assert query.value("notes") == "This is a test transcription"

    def test_update_transcription_name(self, transcription_dao, sample_transcription):
        """Test updating transcription name"""
        # Insert the transcription first
        transcription_dao.insert(sample_transcription)
        
        # Update the name
        new_name = "Updated Transcription Name"
        transcription_dao.update_transcription_name(UUID(sample_transcription.id), new_name)
        
        # Verify the name was updated
        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT name FROM transcription WHERE id = :id")
        query.bindValue(":id", sample_transcription.id)
        assert query.exec()
        assert query.next()
        assert query.value("name") == new_name

    def test_update_transcription_notes(self, transcription_dao, sample_transcription):
        """Test updating transcription notes"""
        # Insert the transcription first
        transcription_dao.insert(sample_transcription)
        
        # Update the notes
        new_notes = "Updated transcription notes with more details"
        transcription_dao.update_transcription_notes(UUID(sample_transcription.id), new_notes)
        
        # Verify the notes were updated
        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT notes FROM transcription WHERE id = :id")
        query.bindValue(":id", sample_transcription.id)
        assert query.exec()
        assert query.next()
        assert query.value("notes") == new_notes

    def test_update_transcription_language(self, transcription_dao, sample_transcription):
        """Test updating transcription language"""
        transcription_dao.insert(sample_transcription)

        transcription_dao.update_transcription_language(
            UUID(sample_transcription.id), "lv"
        )

        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT language FROM transcription WHERE id = :id")
        query.bindValue(":id", sample_transcription.id)
        assert query.exec()
        assert query.next()
        assert query.value("language") == "lv"

    def test_update_transcription_language_nonexistent_id(self, transcription_dao):
        """Test updating language for non-existent transcription ID"""
        with pytest.raises(Exception):
            transcription_dao.update_transcription_language(uuid4(), "lv")

    def test_update_transcription_name_nonexistent_id(self, transcription_dao):
        """Test updating name for non-existent transcription ID"""
        nonexistent_id = uuid4()
        
        # This should raise an exception
        with pytest.raises(Exception):
            transcription_dao.update_transcription_name(nonexistent_id, "New Name")

    def test_update_transcription_notes_nonexistent_id(self, transcription_dao):
        """Test updating notes for non-existent transcription ID"""
        nonexistent_id = uuid4()
        
        # This should raise an exception
        with pytest.raises(Exception):
            transcription_dao.update_transcription_notes(nonexistent_id, "New Notes")

    def test_update_transcription_name_empty_string(self, transcription_dao, sample_transcription):
        """Test updating transcription name to empty string"""
        # Insert the transcription first
        transcription_dao.insert(sample_transcription)
        
        # Update the name to empty string
        transcription_dao.update_transcription_name(UUID(sample_transcription.id), "")
        
        # Verify the name was updated to empty string
        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT name FROM transcription WHERE id = :id")
        query.bindValue(":id", sample_transcription.id)
        assert query.exec()
        assert query.next()
        assert query.value("name") == ""

    def test_update_transcription_notes_empty_string(self, transcription_dao, sample_transcription):
        """Test updating transcription notes to empty string"""
        # Insert the transcription first
        transcription_dao.insert(sample_transcription)
        
        # Update the notes to empty string
        transcription_dao.update_transcription_notes(UUID(sample_transcription.id), "")
        
        # Verify the notes were updated to empty string
        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT notes FROM transcription WHERE id = :id")
        query.bindValue(":id", sample_transcription.id)
        assert query.exec()
        assert query.next()
        assert query.value("notes") == ""

    def test_update_transcription_name_with_none(self, transcription_dao, sample_transcription):
        """Test updating transcription name to None (should be stored as NULL)"""
        # Insert the transcription first
        transcription_dao.insert(sample_transcription)
        
        # Update the name to None
        transcription_dao.update_transcription_name(UUID(sample_transcription.id), None)
        
        # Verify the name was updated to None (NULL in database)
        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT name FROM transcription WHERE id = :id")
        query.bindValue(":id", sample_transcription.id)
        assert query.exec()
        assert query.next()
        # In SQLite, None values are returned as empty strings
        assert query.value("name") == ""

    def test_update_transcription_notes_with_none(self, transcription_dao, sample_transcription):
        """Test updating transcription notes to None (should be stored as NULL)"""
        # Insert the transcription first
        transcription_dao.insert(sample_transcription)
        
        # Update the notes to None
        transcription_dao.update_transcription_notes(UUID(sample_transcription.id), None)
        
        # Verify the notes were updated to None (NULL in database)
        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT notes FROM transcription WHERE id = :id")
        query.bindValue(":id", sample_transcription.id)
        assert query.exec()
        assert query.next()
        # In SQLite, None values are returned as empty strings
        assert query.value("notes") == ""

    def test_insert_transcription_without_name_and_notes(self, transcription_dao):
        """Test inserting a transcription without name and notes (should be NULL)"""
        transcription = Transcription(
            id=str(uuid4()),
            file="/path/to/test.mp3",
            status="completed",
            time_queued="2023-01-01T00:00:00",
            task="TRANSCRIBE",
            model_type="WHISPER"
            # name and notes not provided
        )
        
        transcription_dao.insert(transcription)
        
        # Verify the transcription was inserted with NULL name and notes
        query = QSqlQuery(transcription_dao.db)
        query.prepare("SELECT name, notes FROM transcription WHERE id = :id")
        query.bindValue(":id", transcription.id)
        assert query.exec()
        assert query.next()
        
        # In SQLite, NULL values are returned as empty strings
        assert query.value("name") == ""
        assert query.value("notes") == ""

    def test_database_error_handling(self, transcription_dao):
        """Test that database errors are properly handled"""
        # Mock a database error by using an invalid query
        with patch.object(transcription_dao, '_create_query') as mock_create_query:
            mock_query = Mock()
            mock_query.prepare.return_value = True
            mock_query.bindValue.return_value = None
            mock_query.exec.return_value = False
            mock_query.lastError.return_value.text.return_value = "Database error"
            mock_create_query.return_value = mock_query
            
            # This should raise an exception with the database error message
            with pytest.raises(Exception, match="Database error"):
                transcription_dao.update_transcription_name(uuid4(), "Test Name")

    def test_find_completed_transcription_by_url(self, transcription_dao):
        url = "https://www.youtube.com/watch?v=abc123"
        queued = Transcription(id=str(uuid4()), url=url, status="queued")
        completed = Transcription(id=str(uuid4()), url=url, status="completed")
        other = Transcription(
            id=str(uuid4()), url="https://example.com/other", status="completed"
        )
        for transcription in (queued, completed, other):
            transcription_dao.insert(transcription)

        assert transcription_dao.find_completed_transcription_by_url(url) == completed.id
        assert (
            transcription_dao.find_completed_transcription_by_url(
                "https://example.com/missing"
            )
            is None
        )

    @pytest.mark.parametrize(
        "name", ["audio.mp3", "report_1.mp3", "100%.mp3", "wow!.mp3"]
    )
    def test_find_completed_transcription_by_filename(self, transcription_dao, name):
        queued = Transcription(
            id=str(uuid4()), file=f"/music/in/{name}", status="queued"
        )
        completed = Transcription(
            id=str(uuid4()), file=f"/music/out/{name}", status="completed"
        )
        other = Transcription(
            id=str(uuid4()), file="/music/out/other.mp3", status="completed"
        )
        for transcription in (queued, completed, other):
            transcription_dao.insert(transcription)

        assert (
            transcription_dao.find_completed_transcription_by_filename(name)
            == completed.id
        )
        assert (
            transcription_dao.find_completed_transcription_by_filename("missing.mp3")
            is None
        )

    # Folder watch and Import Folder join paths with os.path.join, which puts a
    # backslash before the file name on Windows. CLI paths are stored as typed.
    @pytest.mark.parametrize(
        "file", [r"C:\Users\me\Music\audio.mp3", r"C:/Users/me/Music\audio.mp3"]
    )
    def test_find_completed_transcription_by_filename_in_windows_path(
        self, transcription_dao, file
    ):
        completed = Transcription(id=str(uuid4()), file=file, status="completed")
        transcription_dao.insert(completed)

        assert (
            transcription_dao.find_completed_transcription_by_filename("audio.mp3")
            == completed.id
        )

    # "_" and "%" are wildcards in LIKE patterns
    @pytest.mark.parametrize(
        "file, name",
        [
            ("/music/report 1.mp3", "report_1.mp3"),
            ("/music/Interview 100 - final cut.mp3", "Interview 100%.mp3"),
        ],
    )
    def test_find_completed_transcription_by_filename_matches_name_literally(
        self, transcription_dao, file, name
    ):
        transcription_dao.insert(
            Transcription(id=str(uuid4()), file=file, status="completed")
        )

        assert transcription_dao.find_completed_transcription_by_filename(name) is None

    # A URL import stores its download, a temp file always named audio.wav,
    # and is looked up by URL
    @pytest.mark.parametrize(
        "file",
        [
            r"C:\Users\me\AppData\Local\Temp\tmpab12cd\audio.wav",
            "/tmp/tmpab12cd/audio.wav",
        ],
    )
    def test_find_completed_transcription_by_filename_ignores_url_imports(
        self, transcription_dao, file
    ):
        transcription_dao.insert(
            Transcription(
                id=str(uuid4()),
                file=file,
                url="https://www.youtube.com/watch?v=abc123",
                status="completed",
            )
        )

        assert (
            transcription_dao.find_completed_transcription_by_filename("audio.wav")
            is None
        )

    # copy_transcription stores "" rather than NULL in url
    def test_find_completed_transcription_by_filename_finds_copies(
        self, transcription_dao
    ):
        original = Transcription(
            id=str(uuid4()), file="/music/audio.wav", status="completed"
        )
        transcription_dao.insert(original)
        copy_id = transcription_dao.copy_transcription(original.id_as_uuid)
        transcription_dao.update_transcription_as_completed(copy_id)

        assert transcription_dao.find_completed_transcription_by_filename(
            "audio.wav"
        ) == str(copy_id)
