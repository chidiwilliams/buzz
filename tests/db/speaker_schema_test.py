import sqlite3

from buzz.db.helpers import run_sqlite_migrations


def test_speaker_column_migration_preserves_existing_transcript_text(tmp_path):
    database_path = tmp_path / "old-buzz.sqlite"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE transcription (
            id TEXT PRIMARY KEY,
            error_message TEXT,
            export_formats TEXT,
            file TEXT,
            output_folder TEXT,
            progress DOUBLE PRECISION DEFAULT 0.0,
            language TEXT,
            model_type TEXT,
            source TEXT,
            status TEXT,
            task TEXT,
            time_ended TIMESTAMP,
            time_queued TIMESTAMP NOT NULL,
            time_started TIMESTAMP,
            url TEXT,
            whisper_model_size TEXT,
            hugging_face_model_id TEXT,
            word_level_timings BOOLEAN DEFAULT FALSE,
            extract_speech BOOLEAN DEFAULT FALSE,
            name TEXT,
            notes TEXT
        );
        CREATE TABLE transcription_segment (
            id INTEGER PRIMARY KEY,
            end_time INT DEFAULT 0,
            start_time INT DEFAULT 0,
            text TEXT NOT NULL,
            translation TEXT DEFAULT '',
            transcription_id TEXT,
            FOREIGN KEY (transcription_id) REFERENCES transcription(id)
                ON DELETE CASCADE
        );
        CREATE INDEX idx_transcription_id
            ON transcription_segment(transcription_id);
        INSERT INTO transcription (id, time_queued)
            VALUES ('transcript-1', '2026-08-19');
        INSERT INTO transcription_segment (
            id, start_time, end_time, text, translation, transcription_id
        ) VALUES (
            1, 0, 1000, 'Nyomi: keep this exact text', '', 'transcript-1'
        );
        """
    )

    run_sqlite_migrations(connection)

    row = connection.execute(
        "SELECT text, speaker FROM transcription_segment WHERE id = 1"
    ).fetchone()
    connection.close()
    assert row == ("Nyomi: keep this exact text", "")
