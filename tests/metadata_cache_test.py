import dataclasses
import json
import os
from collections import namedtuple
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest
from openai.types.audio import Transcription

from buzz import metadata_cache


def strict_json_load(path):
    """Load JSON the way strict parsers do, rejecting NaN and Infinity."""

    def reject(constant):
        raise ValueError(f"Not valid JSON: {constant}")

    with open(path, encoding="utf-8") as file:
        return json.load(file, parse_constant=reject)


class TestPaths:
    def test_files_are_kept_per_transcription(self, metadata_dir):
        transcription_id = uuid4()

        path = metadata_cache.metadata_path(transcription_id, "whisper_cpp")

        assert path == os.path.join(
            str(metadata_dir), str(transcription_id), "whisper_cpp.json"
        )

    def test_defaults_to_the_buzz_cache_folder(self, monkeypatch):
        monkeypatch.delenv(metadata_cache.METADATA_DIR_ENV, raising=False)

        with patch.object(metadata_cache, "user_cache_dir", return_value="/cache/Buzz"):
            assert metadata_cache.metadata_root() == os.path.join("/cache/Buzz", "metadata")

    def test_accepts_string_ids(self, metadata_dir):
        transcription_id = uuid4()

        assert metadata_cache.metadata_dir(str(transcription_id)) == (
            metadata_cache.metadata_dir(transcription_id)
        )

    @pytest.mark.parametrize("transcription_id", ["..", "../other", "", "not-a-uuid"])
    def test_rejects_ids_that_are_not_uuids(self, metadata_dir, transcription_id):
        with pytest.raises(ValueError):
            metadata_cache.metadata_dir(transcription_id)

    @pytest.mark.parametrize(
        "name", ["", "../escape", "sub/name", ".hidden", "name.json", "with space"]
    )
    def test_rejects_names_that_are_not_plain_file_names(self, metadata_dir, name):
        with pytest.raises(ValueError):
            metadata_cache.metadata_path(uuid4(), name)


class TestSaveAndLoad:
    def test_round_trip(self, metadata_dir):
        transcription_id = uuid4()
        data = {"segments": [{"text": "Ģērbies", "no_speech_prob": 0.01}]}

        path = metadata_cache.save_metadata(transcription_id, "engine", data)

        assert os.path.isfile(path)
        assert metadata_cache.load_metadata(transcription_id, "engine") == data
        # Kept readable as UTF-8 for tools other than Buzz
        with open(path, encoding="utf-8") as file:
            assert "Ģērbies" in file.read()

    def test_replaces_earlier_file(self, metadata_dir):
        transcription_id = uuid4()
        metadata_cache.save_metadata(transcription_id, "engine", {"run": 1})

        metadata_cache.save_metadata(transcription_id, "engine", {"run": 2})

        assert metadata_cache.load_metadata(transcription_id, "engine") == {"run": 2}
        # The temp file the write went through is gone
        assert os.listdir(metadata_cache.metadata_dir(transcription_id)) == [
            "engine.json"
        ]

    def test_load_without_file_returns_none(self, metadata_dir):
        assert metadata_cache.load_metadata(uuid4(), "engine") is None

    def test_save_without_transcription_id_does_nothing(self, metadata_dir):
        assert metadata_cache.save_metadata(None, "engine", {"a": 1}) is None
        assert not metadata_dir.exists()

    def test_save_failure_is_logged_not_raised(self, metadata_dir, caplog):
        transcription_id = uuid4()

        with patch.object(
            metadata_cache, "_write_atomically", side_effect=OSError("disk full")
        ):
            assert metadata_cache.save_metadata(transcription_id, "engine", {}) is None

        assert "Failed to save engine metadata" in caplog.text

    def test_failed_write_leaves_no_files_behind(self, metadata_dir):
        transcription_id = uuid4()
        metadata_cache.save_metadata(transcription_id, "engine", {"run": 1})

        with patch.object(metadata_cache.os, "replace", side_effect=OSError("disk full")):
            metadata_cache.save_metadata(transcription_id, "engine", {"run": 2})

        # The earlier file is untouched and no temp file is left over
        assert metadata_cache.load_metadata(transcription_id, "engine") == {"run": 1}
        assert os.listdir(metadata_cache.metadata_dir(transcription_id)) == [
            "engine.json"
        ]

    def test_non_finite_floats_are_saved_as_valid_json(self, metadata_dir):
        transcription_id = uuid4()

        path = metadata_cache.save_metadata(
            transcription_id,
            "speaker_identification",
            {"scores": [float("-inf"), float("nan"), 0.5]},
        )

        assert strict_json_load(path) == {"scores": [None, None, 0.5]}

    def test_save_file_keeps_bytes_as_they_are(self, metadata_dir, tmp_path):
        # whisper-cli can split a multi-byte character between tokens, so its
        # output is not always valid UTF-8 and must not be re-encoded
        source = tmp_path / "output.json"
        content = b'{"tokens": [{"text": "\xe4\xbd"}, {"text": "\xa0"}]}'
        source.write_bytes(content)
        transcription_id = uuid4()

        path = metadata_cache.save_metadata_file(transcription_id, "whisper_cpp", str(source))

        with open(path, "rb") as file:
            assert file.read() == content

    def test_save_file_without_source_is_logged_not_raised(self, metadata_dir, tmp_path):
        transcription_id = uuid4()

        path = metadata_cache.save_metadata_file(
            transcription_id, "whisper_cpp", str(tmp_path / "missing.json")
        )

        assert path is None
        assert metadata_cache.list_metadata(transcription_id) == []


class TestToJsonable:
    def test_dataclasses_and_named_tuples(self):
        @dataclasses.dataclass
        class Word:
            word: str
            probability: float

        Info = namedtuple("Info", ["language", "language_probability"])

        assert metadata_cache.to_jsonable(
            {"words": [Word("hi", 0.9)], "info": Info("en", 0.99)}
        ) == {
            "words": [{"word": "hi", "probability": 0.9}],
            "info": {"language": "en", "language_probability": 0.99},
        }

    def test_numpy_values(self):
        assert metadata_cache.to_jsonable(
            {"array": np.array([1.5, 2.5]), "scalar": np.float32(0.5), "count": np.int64(3)}
        ) == {"array": [1.5, 2.5], "scalar": 0.5, "count": 3}

    def test_openai_responses_keep_fields_buzz_does_not_use(self):
        response = Transcription(
            text="Hello",
            segments=[{"start": 0, "end": 1.5, "text": "Hello", "no_speech_prob": 0.02}],
        )

        data = metadata_cache.to_jsonable(response)

        assert data["text"] == "Hello"
        assert data["segments"][0]["no_speech_prob"] == 0.02

    def test_objects_keep_their_public_attributes(self):
        class Result:
            def __init__(self):
                self.text = "hi"
                self._private = "hidden"

        assert metadata_cache.to_jsonable(Result()) == {"text": "hi"}

    def test_objects_that_answer_every_attribute_do_not_recurse_forever(self):
        data = metadata_cache.to_jsonable({"value": MagicMock()})

        json.dumps(data)

    def test_cyclic_objects_do_not_recurse_forever(self):
        node = {}
        node["self"] = node

        json.dumps(metadata_cache.to_jsonable(node))


class TestListDeleteCopy:
    def test_list_metadata(self, metadata_dir):
        transcription_id = uuid4()
        metadata_cache.save_metadata(transcription_id, "whisper_cpp", {})
        metadata_cache.save_metadata(transcription_id, "speaker_identification", {})

        assert metadata_cache.list_metadata(transcription_id) == [
            "speaker_identification",
            "whisper_cpp",
        ]
        assert metadata_cache.list_metadata(uuid4()) == []

    def test_delete_removes_only_that_transcription(self, metadata_dir):
        deleted_id, kept_id = uuid4(), uuid4()
        metadata_cache.save_metadata(deleted_id, "engine", {"a": 1})
        metadata_cache.save_metadata(kept_id, "engine", {"b": 2})

        metadata_cache.delete_metadata(deleted_id)

        assert not os.path.exists(metadata_cache.metadata_dir(deleted_id))
        assert metadata_cache.load_metadata(kept_id, "engine") == {"b": 2}

    def test_delete_without_metadata_does_nothing(self, metadata_dir):
        metadata_cache.delete_metadata(uuid4())

    def test_delete_with_invalid_id_does_not_touch_the_root(self, metadata_dir):
        metadata_cache.save_metadata(uuid4(), "engine", {})

        metadata_cache.delete_metadata("..")

        assert metadata_dir.exists()

    def test_copy_keeps_files_the_target_already_has(self, metadata_dir):
        source_id, target_id = uuid4(), uuid4()
        metadata_cache.save_metadata(source_id, "whisper_cpp", {"from": "source"})
        metadata_cache.save_metadata(source_id, "speaker_identification", {"from": "source"})
        metadata_cache.save_metadata(target_id, "speaker_identification", {"from": "target"})

        metadata_cache.copy_metadata(source_id, target_id)

        assert metadata_cache.load_metadata(target_id, "whisper_cpp") == {"from": "source"}
        assert metadata_cache.load_metadata(target_id, "speaker_identification") == {
            "from": "target"
        }
        # The source is unchanged
        assert metadata_cache.load_metadata(source_id, "speaker_identification") == {
            "from": "source"
        }

    def test_copy_without_source_metadata_creates_nothing(self, metadata_dir):
        target_id = uuid4()

        metadata_cache.copy_metadata(uuid4(), target_id)

        assert not os.path.exists(metadata_cache.metadata_dir(target_id))
