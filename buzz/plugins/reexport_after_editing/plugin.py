"""
Re-export after editing plugin for Buzz.

When the user closes the transcription viewer after changing a transcript, the
transcript is exported again in the formats chosen when it was transcribed
(``Transcription.export_formats``), to the same folder. Transcripts that were
not exported when they were transcribed are left alone.

Uses the ``on_viewer_closed`` hook, available since Buzz 1.4.6.
"""

import datetime
import logging
import os
from typing import List

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

DEFAULT_FILE_NAME = "{{ input_file_name }} (edited)"


class ReexportAfterEditingPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="reexport_after_editing",
        name=_("Re-export after editing"),
        description=_(
            "When a transcript is changed in the transcript viewer, export it "
            "again in the formats chosen when it was transcribed, once the "
            "viewer is closed. Transcripts that were not exported are skipped."
        ),
        version="1.0.0",
        pip_dependencies=[],
        config_fields=[
            ConfigField(
                key="file_name",
                label=_("File name"),
                type=ConfigFieldType.TEXT,
                default=DEFAULT_FILE_NAME,
                description=_(
                    "Name of the exported files, without extension. Available "
                    "variables: {{ input_file_name }}, {{ task }}, "
                    "{{ language }}, {{ model_type }}, {{ model_size }}, "
                    "{{ date_time }}. A file with the same name is overwritten."
                ),
            ),
        ],
    )

    def on_viewer_closed(self, transcription, modified, context: PluginContext):
        if not modified:
            return

        output_formats = parse_export_formats(transcription.export_formats)
        if not output_formats:
            context.log.debug(
                "Re-export skipped for %s: it was not exported", transcription.id
            )
            return

        folder = transcription.output_folder or (
            os.path.dirname(transcription.file) if transcription.file else ""
        )
        if not folder:
            context.log.info(
                "Re-export skipped for %s: no folder to export to", transcription.id
            )
            return

        segments = to_segments(
            context.transcription_service.get_transcription_segments(
                transcription.id_as_uuid
            )
        )
        if not segments:
            context.log.info("Re-export skipped for %s: no segments", transcription.id)
            return

        from buzz.transcriber.file_transcriber import write_output

        template = (context.config.get("file_name") or "").strip() or DEFAULT_FILE_NAME
        file_name = output_file_name(transcription, template)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            context.log.error("Re-export failed, cannot create %s: %s", folder, exc)
            return

        for output_format in output_formats:
            path = os.path.join(folder, f"{file_name}.{output_format.value}")
            try:
                write_output(path=path, segments=segments, output_format=output_format)
                context.log.info("Re-exported %s", path)
            except Exception as exc:
                context.log.error("Re-export to %s failed: %s", path, exc)


def parse_export_formats(export_formats) -> List:
    """The ``OutputFormat``s of a transcription's ``export_formats`` column."""
    from buzz.transcriber.transcriber import OutputFormat

    formats = []
    for value in (export_formats or "").split(","):
        value = value.strip()
        if not value:
            continue
        try:
            output_format = OutputFormat(value)
        except ValueError:
            logger.warning("Unknown export format %r", value)
            continue
        if output_format not in formats:
            formats.append(output_format)
    return formats


def to_segments(db_segments) -> List:
    """Database segments as the ``Segment``s ``write_output`` writes."""
    from buzz.transcriber.transcriber import Segment

    return [
        Segment(
            start=db_segment.start_time,
            end=db_segment.end_time,
            text=db_segment.text or "",
            translation=db_segment.translation or "",
            speaker=db_segment.speaker or "",
        )
        for db_segment in db_segments
    ]


def output_file_name(transcription, template: str) -> str:
    """Fill in the file name template, like Buzz's export file name."""
    from buzz.paths import safe_filename_component

    input_file_name = transcription.name or os.path.splitext(
        os.path.basename(transcription.file or "")
    )[0]
    # Extracted speech files end with "_speech"
    if not transcription.name and input_file_name.endswith("_speech"):
        input_file_name = input_file_name[: -len("_speech")]

    file_name = (
        template.replace("{{ input_file_name }}", input_file_name)
        .replace("{{ task }}", transcription.task or "")
        .replace("{{ language }}", transcription.language or "")
        .replace("{{ model_type }}", transcription.model_type or "")
        .replace("{{ model_size }}", transcription.whisper_model_size or "")
        .replace(
            "{{ date_time }}",
            datetime.datetime.now().strftime("%d-%b-%Y %H-%M-%S"),
        )
    )
    return safe_filename_component(file_name)
