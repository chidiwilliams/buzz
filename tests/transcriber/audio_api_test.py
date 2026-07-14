from unittest.mock import Mock

from buzz.model_loader import ModelType


def load_audio_api_config():
    from buzz.transcriber.audio_api import load_audio_api_config

    return load_audio_api_config


def default_settings():
    settings = Mock()
    settings.value.side_effect = lambda key, default_value: default_value
    return settings


def test_funasr_defaults_do_not_reuse_openai_key(monkeypatch):
    monkeypatch.delenv("BUZZ_FUNASR_BASE_URL", raising=False)
    monkeypatch.delenv("BUZZ_FUNASR_MODEL", raising=False)
    monkeypatch.delenv("BUZZ_FUNASR_API_KEY", raising=False)

    config = load_audio_api_config()(
        ModelType.FUNASR_API,
        default_settings(),
        openai_access_token="sk-openai",
    )

    assert config.base_url == "http://localhost:8000/v1"
    assert config.model == "sensevoice"
    assert config.api_key == "not-needed"
    assert config.api_key != "sk-openai"
    assert config.supports_translation is False
    assert config.supports_prompt is False


def test_funasr_environment_overrides_settings(monkeypatch):
    monkeypatch.setenv("BUZZ_FUNASR_BASE_URL", "https://asr.example.com/v1")
    monkeypatch.setenv("BUZZ_FUNASR_MODEL", "fun-asr-nano")
    monkeypatch.setenv("BUZZ_FUNASR_API_KEY", "private-token")

    settings = Mock()
    settings.value.side_effect = ["http://settings.example/v1", "paraformer"]
    config = load_audio_api_config()(
        ModelType.FUNASR_API,
        settings,
        openai_access_token="sk-openai",
    )

    assert config.base_url == "https://asr.example.com/v1"
    assert config.model == "fun-asr-nano"
    assert config.api_key == "private-token"
    settings.value.assert_not_called()


def test_openai_configuration_is_unchanged(monkeypatch):
    monkeypatch.delenv("BUZZ_FUNASR_BASE_URL", raising=False)
    monkeypatch.delenv("BUZZ_FUNASR_MODEL", raising=False)
    monkeypatch.delenv("BUZZ_FUNASR_API_KEY", raising=False)

    settings = Mock()
    settings.value.side_effect = ["https://openai.example/v1", "whisper-1"]
    config = load_audio_api_config()(
        ModelType.OPEN_AI_WHISPER_API,
        settings,
        openai_access_token="sk-openai",
    )

    assert config.base_url == "https://openai.example/v1"
    assert config.model == "whisper-1"
    assert config.api_key == "sk-openai"
    assert config.supports_translation is True
    assert config.supports_prompt is True
