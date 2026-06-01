"""Tests for buzz.transcriber.bulk_renamer.

Covers the parts that don't need a real Whisper backend: filename sanitation,
RenamePlan invariants, apply/undo roundtrip, and collision resolution. The
transcription path itself is covered by Buzz's existing
whisper_file_transcriber tests, which the bulk renamer simply reuses.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buzz.transcriber.bulk_renamer import (
    BulkRenamer,
    RenamePlan,
    RenamerConfig,
    apply_plan,
    first_n_words,
    sanitize_filename,
    undo_from_log,
)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitize:
    def test_basic(self):
        assert sanitize_filename("Hello World") == "hello_world"

    def test_punctuation(self):
        assert sanitize_filename("Hello, World! Foo bar.") == "hello_world_foo_bar"

    def test_collapses_whitespace(self):
        assert sanitize_filename("  multiple   spaces  here  ") == "multiple_spaces_here"

    def test_collapses_underscores(self):
        assert sanitize_filename("Lots___of_____underscores") == "lots_of_underscores"

    def test_strips_special_chars(self):
        assert sanitize_filename("Special $%^& chars") == "special_chars"

    def test_empty_input(self):
        assert sanitize_filename("") == ""
        assert sanitize_filename("    ") == ""

    def test_truncates_at_word_boundary(self):
        long = "this is a very long sentence with many many words inside"
        out = sanitize_filename(long, max_length=20)
        assert len(out) <= 20
        # Should not end on an underscore (word boundary cut)
        assert not out.endswith("_")

    def test_unicode_word_chars_preserved(self):
        # Python's \w matches unicode letters by default
        assert sanitize_filename("café résumé") == "café_résumé"


# ---------------------------------------------------------------------------
# first_n_words
# ---------------------------------------------------------------------------

class TestFirstNWords:
    def test_normal(self):
        assert first_n_words("one two three four five", 3) == "one two three"

    def test_fewer_words_than_requested(self):
        assert first_n_words("only two", 5) == "only two"

    def test_empty(self):
        assert first_n_words("", 5) == ""

    def test_zero(self):
        assert first_n_words("hello world", 0) == ""


# ---------------------------------------------------------------------------
# RenamePlan invariants
# ---------------------------------------------------------------------------

class TestRenamePlan:
    def test_will_change_only_when_ready_and_different(self):
        p = RenamePlan(original_path=Path("/tmp/a.mp3"))
        assert not p.will_change

        p.status = "ready"
        p.proposed_path = Path("/tmp/a.mp3")  # same as original
        assert not p.will_change

        p.proposed_path = Path("/tmp/b.mp3")
        assert p.will_change

        p.status = "error"
        assert not p.will_change


# ---------------------------------------------------------------------------
# apply_plan + undo_from_log
# ---------------------------------------------------------------------------

class TestApplyAndUndo:
    @pytest.fixture
    def tmp(self, tmp_path):
        return tmp_path

    def _make(self, dir_: Path, name: str) -> Path:
        p = dir_ / name
        p.write_bytes(b"fake audio")
        return p

    def test_apply_and_undo_roundtrip(self, tmp):
        f1 = self._make(tmp, "raw_foo.mp3")
        f2 = self._make(tmp, "raw_bar.mp3")
        log_path = tmp / ".undo.json"

        plans = [
            RenamePlan(
                original_path=f1, transcript="hello world",
                proposed_name="hello_world",
                proposed_path=tmp / "hello_world.mp3", status="ready",
            ),
            RenamePlan(
                original_path=f2, transcript="foo bar",
                proposed_name="foo_bar",
                proposed_path=tmp / "foo_bar.mp3", status="ready",
            ),
        ]
        summary = apply_plan(plans, log_path)
        assert summary["applied_count"] == 2
        assert (tmp / "hello_world.mp3").exists()
        assert (tmp / "foo_bar.mp3").exists()
        assert not f1.exists() and not f2.exists()
        assert log_path.exists()

        # Undo
        result = undo_from_log(log_path)
        assert result["reverted_count"] == 2
        assert f1.exists() and f2.exists()

    def test_apply_skips_errors_and_no_changes(self, tmp):
        f1 = self._make(tmp, "ok.mp3")
        f2 = self._make(tmp, "nochange.mp3")
        plans = [
            RenamePlan(original_path=f1, status="error", error="api fail"),
            RenamePlan(
                original_path=f2, transcript="nochange",
                proposed_name="nochange",
                proposed_path=f2,  # same as original
                status="ready",
            ),
        ]
        summary = apply_plan(plans, log_path=None)
        assert summary["applied_count"] == 0
        assert summary["skipped_count"] == 2
        assert f1.exists() and f2.exists()


# ---------------------------------------------------------------------------
# Collision resolution (BulkRenamer._resolve_collisions)
# ---------------------------------------------------------------------------

class TestCollisionResolution:
    def _renamer(self, **cfg_kw):
        cfg = RenamerConfig(**cfg_kw)
        # Construct without a parent QObject; we never call .plan_renames here
        return BulkRenamer(cfg)

    def _file(self, dir_: Path, name: str) -> Path:
        p = dir_ / name
        p.write_bytes(b"x")
        return p

    def test_two_plans_want_same_target(self, tmp_path):
        f1 = self._file(tmp_path, "a.mp3")
        f2 = self._file(tmp_path, "b.mp3")
        plans = [
            RenamePlan(
                original_path=f1, status="ready",
                proposed_path=tmp_path / "same.mp3", transcript="same",
            ),
            RenamePlan(
                original_path=f2, status="ready",
                proposed_path=tmp_path / "same.mp3", transcript="same",
            ),
        ]
        self._renamer()._resolve_collisions(plans)
        assert plans[0].proposed_path.name == "same.mp3"
        assert plans[1].proposed_path.name == "same_1.mp3"

    def test_collision_with_existing_disk_file(self, tmp_path):
        f1 = self._file(tmp_path, "a.mp3")
        # Pre-existing file at the target outside the plan
        self._file(tmp_path, "target.mp3")
        plans = [
            RenamePlan(
                original_path=f1, status="ready",
                proposed_path=tmp_path / "target.mp3", transcript="target",
            ),
        ]
        self._renamer()._resolve_collisions(plans)
        assert plans[0].proposed_path.name == "target_1.mp3"

    def test_skip_strategy_marks_plan_skipped(self, tmp_path):
        f1 = self._file(tmp_path, "a.mp3")
        self._file(tmp_path, "target.mp3")
        plans = [
            RenamePlan(
                original_path=f1, status="ready",
                proposed_path=tmp_path / "target.mp3", transcript="target",
            ),
        ]
        self._renamer(collision_strategy="skip")._resolve_collisions(plans)
        assert plans[0].status == "skipped"

    def test_no_op_rename_does_not_collide(self, tmp_path):
        # If a plan's proposed_path == original_path, it's a no-op and must
        # not consume a target slot or trigger collision logic.
        f1 = self._file(tmp_path, "already_correct.mp3")
        f2 = self._file(tmp_path, "b.mp3")
        plans = [
            RenamePlan(
                original_path=f1, status="ready",
                proposed_path=f1, transcript="already correct",
            ),
            RenamePlan(
                original_path=f2, status="ready",
                proposed_path=tmp_path / "already_correct.mp3",
                transcript="already correct",
            ),
        ]
        self._renamer()._resolve_collisions(plans)
        assert plans[0].proposed_path == f1                                  # untouched
        assert plans[1].proposed_path.name == "already_correct_1.mp3"        # bumped


# ---------------------------------------------------------------------------
# find_audio_files
# ---------------------------------------------------------------------------

class TestFindAudioFiles:
    def test_finds_known_extensions_case_insensitive(self, tmp_path):
        for name in ("a.mp3", "b.WAV", "c.flac", "d.txt", "e.MP3"):
            (tmp_path / name).write_bytes(b"x")
        cfg = RenamerConfig()
        files = BulkRenamer(cfg).find_audio_files(tmp_path)
        names = sorted(p.name for p in files)
        assert "a.mp3" in names
        assert "b.WAV" in names
        assert "c.flac" in names
        assert "e.MP3" in names
        assert "d.txt" not in names
