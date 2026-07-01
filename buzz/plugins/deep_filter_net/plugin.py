import os

from buzz.plugins.base import (
    BuzzPlugin,
    ConfigField,
    ConfigFieldType,
    PluginContext,
    PluginMetadata,
    plugin_gettext,
)

_ = plugin_gettext(__file__)


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)


class DeepFilterNetPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="deep_filter_net",
        name=_("DeepFilterNet Noise Reduction"),
        description=_("Removes background noise using DeepFilterNet3 before transcription."),
        version="1.0.0",
        pip_dependencies=["deepfilternet>=0.5.6"],
        config_fields=[
            ConfigField(
                key="keep_denoised_file",
                label=_("Keep denoised file after transcription"),
                type=ConfigFieldType.BOOL,
                default=False,
            ),
        ],
    )

    def before_transcription(self, task, context: PluginContext):
        try:
            from df.enhance import enhance, init_df, load_audio, save_audio

            input_path = task.file_path
            stem, _ = os.path.splitext(input_path)
            output_path = f"{stem}_DeepFilterNet3.wav"

            context.log.info(f"DeepFilterNet: denoising {input_path} -> {output_path}")

            model, df_state, _ = init_df()
            audio, _ = load_audio(input_path, sr=df_state.sr())
            enhanced = enhance(model, df_state, audio)
            save_audio(output_path, enhanced, df_state.sr())

            return output_path
        except Exception as e:
            context.log.error(f"DeepFilterNet failed: {e}")
            return None

    def on_complete(self, transcription_id, task, segments, context: PluginContext):
        if _coerce_bool(context.config.get("keep_denoised_file", False)):
            return
        file_path = task.file_path or ""
        stem, _ = os.path.splitext(file_path)
        if stem.endswith("_DeepFilterNet3"):
            try:
                os.unlink(file_path)
                context.log.info(f"DeepFilterNet: removed denoised file {file_path}")
            except Exception as e:
                context.log.warning(f"DeepFilterNet: could not remove {file_path}: {e}")
