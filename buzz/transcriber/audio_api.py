import os
from dataclasses import dataclass
from typing import Optional

from buzz.model_loader import ModelType
from buzz.settings.settings import Settings

DEFAULT_FUNASR_API_BASE_URL = "http://localhost:8000/v1"
DEFAULT_FUNASR_API_MODEL = "sensevoice"


@dataclass(frozen=True)
class AudioAPIConfig:
    base_url: Optional[str]
    api_key: str
    model: str
    supports_translation: bool
    supports_prompt: bool


def load_audio_api_config(
    model_type: ModelType,
    settings: Settings,
    openai_access_token: str,
) -> AudioAPIConfig:
    if model_type == ModelType.FUNASR_API:
        return AudioAPIConfig(
            base_url=(
                os.getenv("BUZZ_FUNASR_BASE_URL")
                or settings.value(
                    Settings.Key.FUNASR_API_BASE_URL,
                    DEFAULT_FUNASR_API_BASE_URL,
                )
                or DEFAULT_FUNASR_API_BASE_URL
            ),
            api_key=os.getenv("BUZZ_FUNASR_API_KEY") or "not-needed",
            model=(
                os.getenv("BUZZ_FUNASR_MODEL")
                or settings.value(
                    Settings.Key.FUNASR_API_MODEL,
                    DEFAULT_FUNASR_API_MODEL,
                )
                or DEFAULT_FUNASR_API_MODEL
            ),
            supports_translation=False,
            supports_prompt=False,
        )

    if model_type == ModelType.OPEN_AI_WHISPER_API:
        base_url = settings.value(
            Settings.Key.CUSTOM_OPENAI_BASE_URL,
            "",
        )
        return AudioAPIConfig(
            base_url=base_url or None,
            api_key=openai_access_token,
            model=settings.value(
                Settings.Key.OPENAI_API_MODEL,
                "whisper-1",
            ),
            supports_translation=True,
            supports_prompt=True,
        )

    raise ValueError(f"Unsupported audio API model type: {model_type.value}")
