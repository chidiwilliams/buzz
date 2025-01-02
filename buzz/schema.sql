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
    extract_speech BOOLEAN DEFAULT FALSE
);

CREATE TABLE transcription_segment (
    id INTEGER PRIMARY KEY,
    end_time INT DEFAULT 0,
    start_time INT DEFAULT 0,
    text TEXT NOT NULL,
    translation TEXT DEFAULT '',
    transcription_id TEXT,
    FOREIGN KEY (transcription_id) REFERENCES transcription(id) ON DELETE CASCADE
);
CREATE INDEX idx_transcription_id ON transcription_segment(transcription_id);
