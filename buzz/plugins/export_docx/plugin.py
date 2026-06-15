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
from xml.sax.saxutils import escape

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

# Same default gap (ms) used by the TXT exporter to split paragraphs.
PARAGRAPH_SPLIT_TIME = 2000

_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.'
    'wordprocessingml.document.main+xml"/>'
    "</Types>"
)

_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)

_DOCUMENT_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>{body}<w:sectPr/></w:body>"
    "</w:document>"
)


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
        import zipfile

        from buzz.transcriber.file_transcriber import to_timestamp

        paragraphs = [_heading_xml(title)]

        if include_timestamps:
            for segment in segments:
                text = segment.text.strip()
                if not text:
                    continue
                stamp = (
                    f"[{to_timestamp(segment.start_time)} --> "
                    f"{to_timestamp(segment.end_time)}]"
                )
                paragraphs.append(
                    _paragraph_xml([(stamp + " ", True), (text, False)])
                )
        else:
            # Group into paragraphs on long gaps, mirroring the TXT exporter.
            current = []
            previous_end = None
            for segment in segments:
                if (
                    previous_end is not None
                    and (segment.start_time - previous_end) >= PARAGRAPH_SPLIT_TIME
                    and current
                ):
                    paragraphs.append(_paragraph_xml([(" ".join(current), False)]))
                    current = []
                text = segment.text.strip()
                if text:
                    current.append(text)
                previous_end = segment.end_time
            if current:
                paragraphs.append(_paragraph_xml([(" ".join(current), False)]))

        document_xml = _DOCUMENT_TEMPLATE.format(body="".join(paragraphs))

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as docx:
            docx.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
            docx.writestr("_rels/.rels", _RELS_XML)
            docx.writestr("word/document.xml", document_xml)


def _run_xml(text, bold):
    props = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _paragraph_xml(runs):
    return "<w:p>" + "".join(_run_xml(text, bold) for text, bold in runs) + "</w:p>"


def _heading_xml(title):
    return (
        '<w:p><w:pPr><w:spacing w:after="200"/></w:pPr>'
        '<w:r><w:rPr><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr>'
        f'<w:t xml:space="preserve">{escape(title)}</w:t></w:r></w:p>'
    )


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)