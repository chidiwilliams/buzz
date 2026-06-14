"""
AI Summary plugin for Buzz.

After a transcription completes, sends the transcript text to an OpenAI-compatible
chat completions API and stores the resulting summary in the transcription's
Notes field and/or a text file next to a chosen output folder.

This is the reference plugin shipped with Buzz to exercise the plugin
infrastructure. It declares no pip dependencies because the ``openai`` package is
already bundled with Buzz.
"""

import logging
import os

from buzz.plugins.base import (
    BuzzPlugin,
    ConfigField,
    ConfigFieldType,
    PluginContext,
    PluginMetadata,
    plugin_gettext,
)

logger = logging.getLogger(__name__)

# Translator for this plugin's user-facing strings. Translations live in
# ``locale/<locale>.json`` next to this file; missing strings fall through.
_ = plugin_gettext(__file__)

DEFAULT_PROMPT = (
    "You are a helpful assistant. Summarise the following transcript into a "
    "concise set of key points and action items. Use clear, plain language."
)


class AISummaryPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="ai_summary",
        name=_("AI Summary"),
        description=_(
            "Generate an AI summary of the transcript via an OpenAI-compatible "
            "API and save it to the Notes field and/or a file."
        ),
        version="1.0.0",
        pip_dependencies=[],
        config_fields=[
            ConfigField(
                key="api_url",
                label=_("API base URL"),
                type=ConfigFieldType.TEXT,
                default="https://api.openai.com/v1",
                placeholder="https://api.openai.com/v1",
            ),
            ConfigField(
                key="api_key",
                label=_("API key"),
                type=ConfigFieldType.PASSWORD,
                default="",
                placeholder="sk-...",
            ),
            ConfigField(
                key="model",
                label=_("Model"),
                type=ConfigFieldType.TEXT,
                default="gpt-4o-mini",
            ),
            ConfigField(
                key="prompt",
                label=_("Summarization prompt"),
                type=ConfigFieldType.TEXTAREA,
                default=DEFAULT_PROMPT,
            ),
            ConfigField(
                key="save_to_notes",
                label=_("Save summary to Notes"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="save_to_file",
                label=_("Save summary to a file"),
                type=ConfigFieldType.BOOL,
                default=False,
            ),
            ConfigField(
                key="output_folder",
                label=_("Output folder (for file)"),
                type=ConfigFieldType.TEXT,
                default="",
            ),
        ],
    )

    def on_complete(self, transcription_id, task, segments, context: PluginContext):
        cfg = context.config
        api_key = (cfg.get("api_key") or "").strip()
        if not api_key:
            context.log.warning("AI Summary skipped: no API key configured")
            return

        transcript = "\n".join(
            segment.text for segment in segments if getattr(segment, "text", "")
        ).strip()
        if not transcript:
            context.log.info("AI Summary skipped: empty transcript")
            return

        summary = self._summarize(cfg, transcript, context)
        if not summary:
            return

        if _coerce_bool(cfg.get("save_to_notes", True)):
            try:
                context.transcription_service.update_transcription_notes(
                    transcription_id, summary
                )
            except Exception as exc:
                context.log.error("Failed to save summary to notes: %s", exc)

        if _coerce_bool(cfg.get("save_to_file", False)):
            self._write_file(cfg, task, summary, context)

    def _summarize(self, cfg, transcript, context):
        try:
            from openai import OpenAI
        except ImportError:
            context.log.error("openai package not available")
            return None

        base_url = (cfg.get("api_url") or "").strip() or None
        model = (cfg.get("model") or "gpt-4o-mini").strip()
        prompt = (cfg.get("prompt") or DEFAULT_PROMPT).strip()

        try:
            client = OpenAI(api_key=cfg["api_key"], base_url=base_url, max_retries=0)
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": transcript},
                ],
                timeout=120.0,
            )
        except Exception as exc:
            context.log.error("AI Summary request failed: %s", exc)
            return None

        if completion and completion.choices and completion.choices[0].message:
            return completion.choices[0].message.content
        context.log.error("AI Summary: empty response from server")
        return None

    def _write_file(self, cfg, task, summary, context):
        try:
            source_path = task.file_path or task.original_file_path or "transcript"
            stem = os.path.splitext(os.path.basename(source_path))[0]
            folder = (cfg.get("output_folder") or "").strip()
            if not folder:
                folder = os.path.dirname(source_path) or os.getcwd()
            os.makedirs(folder, exist_ok=True)
            out_path = os.path.join(folder, f"{stem}.summary.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(summary)
            context.log.info("AI Summary written to %s", out_path)
        except Exception as exc:
            context.log.error("Failed to write summary file: %s", exc)


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
