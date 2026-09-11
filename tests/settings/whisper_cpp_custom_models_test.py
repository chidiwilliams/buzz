import os

import pytest
from PyQt6.QtCore import QSettings

from buzz.model_loader import (
    ModelType,
    TranscriptionModel,
    WhisperModelSize,
    get_whisper_cpp_file_path,
)
from buzz.settings import whisper_cpp_custom_models as registry
from buzz.settings.whisper_cpp_custom_models import (
    LEGACY_CUSTOM_MODEL_FILENAME,
    LEGACY_CUSTOM_MODEL_ID,
    add_custom_model,
    get_custom_model,
    get_custom_models,
    is_registered_model_file,
    remove_custom_model,
)


def _write_model_file(path: str, magic: bytes = b"ggml") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as model_file:
        model_file.write(magic + b"\x00" * 128)
    return path


@pytest.fixture()
def isolated_registry(tmp_path, monkeypatch):
    """Back the registry with a throwaway ini file so tests don't touch real settings."""
    ini_path = str(tmp_path / "settings.ini")

    def _settings():
        return QSettings(ini_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(registry, "_settings", _settings)
    return tmp_path


class TestRegistry:
    def test_add_and_get_multiple_models(self, isolated_registry):
        turbo = add_custom_model(name="Hebrew Turbo", path=r"C:\models\turbo.bin")
        v3 = add_custom_model(name="Hebrew v3", path=r"C:\models\v3.bin")

        assert turbo.id != v3.id
        models = get_custom_models(str(isolated_registry))
        assert [m.name for m in models] == ["Hebrew Turbo", "Hebrew v3"]
        assert get_custom_model(str(isolated_registry), turbo.id).path == r"C:\models\turbo.bin"
        assert get_custom_model(str(isolated_registry), v3.id).path == r"C:\models\v3.bin"

    def test_supports_many_models_without_arbitrary_limit(self, isolated_registry):
        for index in range(20):
            add_custom_model(name=f"Model {index}", path=rf"C:\models\{index}.bin")
        assert len(get_custom_models(str(isolated_registry))) == 20

    def test_models_persist_across_reload(self, isolated_registry):
        model = add_custom_model(name="Persisted", path=r"C:\models\persisted.bin")
        # Reading through a fresh call re-reads from the backing store.
        reloaded = get_custom_model(str(isolated_registry), model.id)
        assert reloaded is not None
        assert reloaded.name == "Persisted"

    def test_remove_only_targets_one_model(self, isolated_registry):
        turbo = add_custom_model(name="Hebrew Turbo", path=r"C:\models\turbo.bin")
        v3 = add_custom_model(name="Hebrew v3", path=r"C:\models\v3.bin")

        remove_custom_model(turbo.id)

        remaining = get_custom_models(str(isolated_registry))
        assert [m.id for m in remaining] == [v3.id]

    def test_is_registered_model_file(self, isolated_registry):
        add_custom_model(name="Local", path=str(isolated_registry / "local.bin"))
        assert is_registered_model_file(str(isolated_registry), str(isolated_registry / "local.bin"))
        assert not is_registered_model_file(str(isolated_registry), str(isolated_registry / "other.bin"))


class TestLegacyCompatibility:
    def test_legacy_model_file_is_surfaced(self, isolated_registry):
        legacy_path = _write_model_file(
            os.path.join(str(isolated_registry), LEGACY_CUSTOM_MODEL_FILENAME)
        )
        models = get_custom_models(str(isolated_registry))
        assert len(models) == 1
        assert models[0].id == LEGACY_CUSTOM_MODEL_ID
        assert models[0].path == legacy_path

    def test_no_legacy_entry_when_file_absent(self, isolated_registry):
        assert get_custom_models(str(isolated_registry)) == []


class TestPathResolution:
    def test_custom_id_resolves_to_registered_path(self, isolated_registry):
        model = add_custom_model(name="Hebrew Turbo", path=r"C:\models\turbo.bin")
        assert (
            get_whisper_cpp_file_path(WhisperModelSize.CUSTOM, custom_model_id=model.id)
            == r"C:\models\turbo.bin"
        )

    def test_missing_custom_id_resolves_empty(self, isolated_registry):
        assert (
            get_whisper_cpp_file_path(WhisperModelSize.CUSTOM, custom_model_id="does-not-exist")
            == ""
        )

    def test_no_custom_id_uses_legacy_fixed_path(self, isolated_registry):
        legacy = get_whisper_cpp_file_path(WhisperModelSize.CUSTOM)
        assert legacy.endswith(LEGACY_CUSTOM_MODEL_FILENAME)

    def test_object_without_custom_model_id_attr_still_resolves(self, isolated_registry):
        # Simulates a TranscriptionModel unpickled from an older Buzz version.
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.CUSTOM,
        )
        del model.custom_model_id
        resolved = get_whisper_cpp_file_path(
            model.whisper_model_size,
            custom_model_id=getattr(model, "custom_model_id", None),
        )
        assert resolved.endswith(LEGACY_CUSTOM_MODEL_FILENAME)
