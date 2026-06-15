"""
Enhanced language detection plugin for Buzz.

When a file is queued for transcription with the language left on auto-detect,
this plugin runs a fast ``whisper.cpp --detect-language`` pass before the
transcription starts. It uses the largest whisper.cpp model already downloaded
on the machine, or downloads the ``tiny`` model if none are available.

The detected language code is written back to
``task.transcription_options.language`` so it (a) drives the actual
transcription and (b) renders the ``{{ language }}`` placeholder in exported
file names. The database record is also updated so the language shows up when
exporting later from the transcription viewer.

If the user explicitly picked a language, detection is skipped.
"""

import logging

from buzz.plugins.base import (
    BuzzPlugin,
    ConfigField,
    ConfigFieldType,
    PluginContext,
    PluginMetadata,
    plugin_gettext,
)

logger = logging.getLogger(__name__)

_ = plugin_gettext(__file__)


class EnhancedLanguageDetectionPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="enhanced_language_detection",
        name=_("Enhanced language detection"),
        description=_(
            "Detect the spoken language with whisper.cpp before transcription "
            "(using the largest downloaded model, or the tiny model otherwise) "
            "and use it for the transcription and exported file names. Only runs "
            "when the language is set to auto-detect."
        ),
        version="1.0.0",
        config_fields=[
            ConfigField(
                key="download_tiny_if_missing",
                label=_("Download tiny model if none available"),
                type=ConfigFieldType.BOOL,
                default=True,
                description=_(
                    "If no whisper.cpp model is downloaded, download the tiny "
                    "model to use for language detection."
                ),
            ),
        ],
    )

    def before_transcription(self, task, context: PluginContext):
        options = getattr(task, "transcription_options", None)
        if options is None:
            return None

        # Respect an explicit language choice; only detect when on auto. "en" is
        # the default value used when no language is selected, so it is treated
        # as auto and detection still runs.
        if options.language and options.language.lower() != "en":
            context.log.debug(
                "Enhanced language detection skipped: language already set to '%s'",
                options.language,
            )
            return None

        if not task.file_path:
            context.log.debug("Enhanced language detection skipped: no audio file")
            return None

        model_path = self._resolve_model_path(context)
        if model_path is None:
            context.log.warning(
                "Enhanced language detection skipped: no whisper.cpp model available"
            )
            return None

        try:
            from buzz.transcriber.whisper_cpp import WhisperCpp

            detected = WhisperCpp.detect_language(task.file_path, model_path)
        except Exception as exc:
            context.log.error("Language detection failed: %s", exc, exc_info=True)
            return None

        if not detected:
            context.log.info("Language detection did not return a language")
            return None

        context.log.info("Detected language: %s", detected)

        # Forces the transcription language and flows to the auto-export filename
        # via the same task object the exporter reads.
        options.language = detected

        # Update the persisted record so the transcription viewer export also
        # picks up the detected language.
        try:
            context.transcription_service.update_transcription_language(
                task.uid, detected
            )
        except Exception as exc:
            context.log.error(
                "Failed to persist detected language: %s", exc, exc_info=True
            )

        # Audio is left unchanged.
        return None

    def _resolve_model_path(self, context: PluginContext):
        """Return the path to the largest available whisper.cpp model, or the
        tiny model (downloading it if needed)."""
        from buzz.model_loader import (
            ModelType,
            TranscriptionModel,
            WhisperModelSize,
            WHISPER_MODEL_SIZES,
        )

        best_path = None
        best_size = -1
        # CUSTOM and LUMII are special-purpose models, not general size variants,
        # so they are excluded from language detection.
        skip_sizes = {WhisperModelSize.CUSTOM, WhisperModelSize.LUMII}
        for model_size in WhisperModelSize:
            if model_size in skip_sizes:
                continue
            model = TranscriptionModel(
                model_type=ModelType.WHISPER_CPP,
                whisper_model_size=model_size,
            )
            try:
                path = model.get_local_model_path()
            except Exception:
                path = None
            if not path:
                continue
            rank = WHISPER_MODEL_SIZES.get(model_size, 0)
            if rank > best_size:
                best_size = rank
                best_path = path

        if best_path is not None:
            return best_path

        if not _coerce_bool(context.config.get("download_tiny_if_missing", True)):
            return None

        from buzz.model_loader import ModelDownloader

        context.log.info("No whisper.cpp model found, downloading tiny model")
        model = TranscriptionModel(
            model_type=ModelType.WHISPER_CPP,
            whisper_model_size=WhisperModelSize.TINY,
        )
        try:
            ModelDownloader(model=model).run()
        except Exception as exc:
            context.log.error("Failed to download tiny model: %s", exc, exc_info=True)
            return None

        return model.get_local_model_path()


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
