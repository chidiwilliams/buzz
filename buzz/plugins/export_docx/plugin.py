"""
Export to DOCX plugin for Buzz.

After a transcription completes, writes the transcript to a Microsoft Word
``.docx`` file next to the source media (or in a configured folder). Optionally
includes per-segment timestamps. Otherwise the text is grouped into paragraphs
using the same gap rule as Buzz's plain-text export.

The ``.docx`` is built directly from the standard library (``zipfile`` plus a
handful of XML parts), so the plugin has no third-party dependencies. This keeps
it working in the frozen app, where binary wheels such as ``python-docx``'s
``lxml`` dependency fail to load from the plugin dependency cache.
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

_ = plugin_gettext(__file__)


class ExportDocxPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="export_docx",
        name=_("Export to DOCX"),
        description=_(
            "Export the transcript to a Microsoft Word (.docx) file after "
            "transcription, optionally including timestamps."
        ),
        version="1.0.0",
        pip_dependencies=[],
        config_fields=[
            ConfigField(
                key="output_folder",
                label=_("Output folder"),
                type=ConfigFieldType.TEXT,
                default="",
                description=_("Leave empty to save next to the source file."),
            ),
            ConfigField(
                key="include_timestamps",
                label=_("Include timestamps"),
                type=ConfigFieldType.BOOL,
                default=False,
            ),
        ],
    )

    def on_complete(self, transcription_id, task, segments, context: PluginContext):
        db_segments = context.transcription_service.get_transcription_segments(
            transcription_id=transcription_id
        )
        if not db_segments:
            context.log.info("Export to DOCX skipped: no segments")
            return

        # Prefer the original source path. When "Extract speech" is enabled,
        # task.file_path points at the temporary "_speech.mp3"; original_file_path
        # holds the real source, so the file name and heading match it.
        source_path = (
            getattr(task, "original_file_path", None)
            or task.file_path
            or "transcript"
        )
        stem = os.path.splitext(os.path.basename(source_path))[0] or "transcript"

        folder = (context.config.get("output_folder") or "").strip()
        if not folder:
            folder = os.path.dirname(source_path) or os.getcwd()

        try:
            os.makedirs(folder, exist_ok=True)
            out_path = os.path.join(folder, f"{stem}.docx")
            self._write_docx(
                out_path,
                stem,
                db_segments,
                _coerce_bool(context.config.get("include_timestamps", False)),
            )
            context.log.info("Export to DOCX written to %s", out_path)
        except Exception as exc:
            context.log.error("Export to DOCX failed: %s", exc)

    def _write_docx(self, out_path, title, segments, include_timestamps):
        from buzz.transcriber.docx_writer import write_plain_docx

        write_plain_docx(
            out_path,
            title,
            segments,
            include_timestamps,
        )


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
