import logging
import os
import re
from pathlib import Path
from typing import List, Optional

from buzz.plugins.base import (
    BuzzPlugin,
    ConfigField,
    ConfigFieldType,
    PluginContext,
    PluginMetadata,
    plugin_gettext,
)

_ = plugin_gettext(__file__)

logger = logging.getLogger(__name__)


class SkipAlreadyTranscribedPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="skip_already_transcribed",
        name=_("Skip Already Transcribed"),
        description=_(
            "Skip transcription if results already exist on disk or in the database"
        ),
        config_fields=[
            ConfigField(
                key="check_result_files",
                label=_("Check for existing result files"),
                type=ConfigFieldType.BOOL,
                default=True,
                description=_(
                    "Skip if a .txt, .srt, or .vtt file matching the audio filename is found next to it"
                ),
            ),
            ConfigField(
                key="check_database",
                label=_("Check in transcription database"),
                type=ConfigFieldType.BOOL,
                default=False,
                description=_(
                    "Skip if this file has already been transcribed and the record exists in the database"
                ),
            ),
        ],
    )

    def check_skip(
        self, task, context: PluginContext
    ) -> Optional[List]:
        file_path = task.original_file_path or task.file_path
        if not file_path:
            return None

        if context.config.get("check_result_files"):
            segments = self._find_result_file_segments(file_path, task, context)
            if segments is not None:
                context.log.info(
                    "Skipping transcription: found existing result file for %s",
                    os.path.basename(file_path),
                )
                return segments

        if context.config.get("check_database"):
            segments = self._find_db_segments(file_path, context)
            if segments is not None:
                context.log.info(
                    "Skipping transcription: found prior DB record for %s",
                    os.path.basename(file_path),
                )
                return segments

        return None

    def _find_result_file_segments(self, file_path: str, task, context: PluginContext):
        from buzz.transcriber.transcriber import OutputFormat

        stem = Path(file_path).stem
        if stem.endswith("_speech"):
            stem = stem[:-7]

        search_dirs = [Path(file_path).parent]
        if task.output_directory:
            search_dirs.append(Path(task.output_directory))

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for fmt in OutputFormat:
                for candidate in search_dir.glob(f"{stem}*.{fmt.value}"):
                    segments = self._parse_result_file(candidate, fmt, context)
                    if segments is not None:
                        return segments
        return None

    def _parse_result_file(self, path: Path, fmt, context: PluginContext):
        from buzz.transcriber.transcriber import OutputFormat, Segment

        try:
            text = path.read_text(encoding="utf-8")
            if fmt == OutputFormat.TXT:
                if not text.strip():
                    return None
                return [Segment(start=0, end=0, text=text.strip())]
            elif fmt == OutputFormat.SRT:
                return self._parse_srt(text) or None
            elif fmt == OutputFormat.VTT:
                return self._parse_vtt(text) or None
        except Exception as exc:
            context.log.warning("Failed to parse result file %s: %s", path, exc)
        return None

    def _parse_srt(self, text: str) -> List:
        from buzz.transcriber.transcriber import Segment

        segments = []
        blocks = re.split(r"\n\n+", text.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            m = re.match(
                r"(\d+:\d+:\d+,\d+) --> (\d+:\d+:\d+,\d+)", lines[1]
            )
            if not m:
                continue
            start = self._ts_to_ms(m.group(1).replace(",", "."))
            end = self._ts_to_ms(m.group(2).replace(",", "."))
            body = "\n".join(lines[2:])
            segments.append(Segment(start=start, end=end, text=body))
        return segments

    def _parse_vtt(self, text: str) -> List:
        from buzz.transcriber.transcriber import Segment

        segments = []
        blocks = re.split(r"\n\n+", text.strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 2:
                continue
            m = re.match(
                r"(\d+:\d+:\d+\.\d+) --> (\d+:\d+:\d+\.\d+)", lines[0]
            )
            if not m:
                continue
            start = self._ts_to_ms(m.group(1))
            end = self._ts_to_ms(m.group(2))
            body = "\n".join(lines[1:])
            segments.append(Segment(start=start, end=end, text=body))
        return segments

    def _ts_to_ms(self, ts: str) -> int:
        parts = ts.split(":")
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        return int((h * 3600 + m * 60 + s) * 1000)

    def _find_db_segments(self, file_path: str, context: PluginContext):
        from buzz.transcriber.transcriber import Segment

        filename = os.path.basename(file_path)
        try:
            tid = context.transcription_service.find_completed_transcription_by_filename(
                filename
            )
            if tid is None:
                return None
            raw = context.transcription_service.get_transcription_segments(tid)
            return [
                Segment(start=s.start_time, end=s.end_time, text=s.text)
                for s in raw
            ]
        except Exception as exc:
            context.log.warning("DB check failed: %s", exc)
            return None
