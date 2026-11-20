import json
import logging
import os
import uuid

import pytest

from buzz.db.entity.transcription import Transcription
from buzz.db.entity.transcription_segment import TranscriptionSegment
from buzz.plugins.base import PluginContext
from buzz.plugins.reexport_after_editing import plugin as reexport
from buzz.transcriber.transcriber import OutputFormat

LOCALES = [
    "ca_ES", "da_DK", "de_DE", "es_ES", "fr", "it_IT", "ja_JP", "lv_LV", "nl",
    "pl_PL", "pt_BR", "ru", "tr_TR", "uk_UA", "zh_CN", "zh_TW",
]
PLUGIN_DIR = os.path.dirname(reexport.__file__)


class _Service:
    def __init__(self, segments):
        self.segments = segments
        self.requested = []

    def get_transcription_segments(self, transcription_id):
        self.requested.append(transcription_id)
        return self.segments


def _segments():
    return [
        TranscriptionSegment(0, 1500, "Hello world.", "", "tid", speaker="Alice"),
        TranscriptionSegment(1500, 3000, "Edited text.", "", "tid"),
    ]


def _context(service, file_name=None):
    config = {} if file_name is None else {"file_name": file_name}
    return PluginContext(
        config=config,
        transcription_service=service,
        settings=None,
        logger=logging.getLogger("test"),
    )


def _transcription(tmp_path, **kwargs):
    values = dict(
        id=str(uuid.uuid4()),
        file=str(tmp_path / "interview.mp3"),
        export_formats="txt, srt",
        output_folder=None,
        status="completed",
    )
    values.update(kwargs)
    return Transcription(**values)


def test_loads_as_bundled_plugin():
    from buzz.plugins import loader

    plugin = loader.load_plugin_from_dir(PLUGIN_DIR)
    assert plugin.metadata.id == "reexport_after_editing"
    assert plugin.metadata.pip_dependencies == []
    assert "reexport_after_editing" in loader.BUNDLED_PLUGIN_IDS


def test_reexports_edited_transcript_in_original_formats(tmp_path):
    transcription = _transcription(tmp_path)
    service = _Service(_segments())

    reexport.ReexportAfterEditingPlugin().on_viewer_closed(
        transcription, True, _context(service)
    )

    assert service.requested == [transcription.id_as_uuid]
    assert sorted(os.listdir(tmp_path)) == [
        "interview (edited).srt",
        "interview (edited).txt",
    ]
    txt = (tmp_path / "interview (edited).txt").read_text(encoding="utf-8")
    assert txt.strip() == "Alice: Hello world. Edited text."
    srt = (tmp_path / "interview (edited).srt").read_text(encoding="utf-8")
    assert "00:00:01,500 --> 00:00:03,000\nEdited text." in srt


def test_overwrites_the_previous_reexport(tmp_path):
    transcription = _transcription(tmp_path, export_formats="txt")
    plugin = reexport.ReexportAfterEditingPlugin()
    plugin.on_viewer_closed(transcription, True, _context(_Service(_segments())))

    changed = [TranscriptionSegment(0, 1000, "Changed again.", "", "tid")]
    plugin.on_viewer_closed(transcription, True, _context(_Service(changed)))

    assert os.listdir(tmp_path) == ["interview (edited).txt"]
    assert (tmp_path / "interview (edited).txt").read_text(
        encoding="utf-8"
    ).strip() == "Changed again."


@pytest.mark.parametrize("export_formats", [None, "", " "])
def test_skips_transcript_that_was_not_exported(tmp_path, export_formats):
    transcription = _transcription(tmp_path, export_formats=export_formats)
    service = _Service(_segments())

    reexport.ReexportAfterEditingPlugin().on_viewer_closed(
        transcription, True, _context(service)
    )

    assert service.requested == []
    assert os.listdir(tmp_path) == []


def test_skips_unmodified_transcript(tmp_path):
    service = _Service(_segments())

    reexport.ReexportAfterEditingPlugin().on_viewer_closed(
        _transcription(tmp_path), False, _context(service)
    )

    assert service.requested == []
    assert os.listdir(tmp_path) == []


def test_uses_output_folder_name_and_file_name_template(tmp_path):
    output_folder = tmp_path / "exports"
    transcription = _transcription(
        tmp_path,
        export_formats="vtt",
        output_folder=str(output_folder),
        name="My: meeting",
        task="transcribe",
        language="en",
    )

    reexport.ReexportAfterEditingPlugin().on_viewer_closed(
        transcription,
        True,
        _context(_Service(_segments()), "{{ input_file_name }} - {{ language }} {{ task }}"),
    )

    # The folder is created, invalid file name characters are replaced
    assert os.listdir(output_folder) == ["My_ meeting - en transcribe.vtt"]
    assert (output_folder / "My_ meeting - en transcribe.vtt").read_text(
        encoding="utf-8"
    ).startswith("WEBVTT")


def test_speech_suffix_is_removed_from_the_file_name(tmp_path):
    transcription = _transcription(
        tmp_path, file=str(tmp_path / "talk_speech.mp3"), export_formats="txt"
    )

    reexport.ReexportAfterEditingPlugin().on_viewer_closed(
        transcription, True, _context(_Service(_segments()))
    )

    assert os.listdir(tmp_path) == ["talk (edited).txt"]


def test_parse_export_formats_ignores_unknown_and_duplicates():
    assert reexport.parse_export_formats("srt, docx, txt,srt") == [
        OutputFormat.SRT,
        OutputFormat.TXT,
    ]


def test_skips_without_segments_or_folder(tmp_path):
    plugin = reexport.ReexportAfterEditingPlugin()
    plugin.on_viewer_closed(_transcription(tmp_path), True, _context(_Service([])))
    assert os.listdir(tmp_path) == []

    service = _Service(_segments())
    plugin.on_viewer_closed(
        _transcription(tmp_path, file=None), True, _context(service)
    )
    assert service.requested == []


def test_has_translations_for_every_locale(monkeypatch):
    import buzz.plugins.base as base
    from buzz.plugins import loader

    monkeypatch.setattr(base, "_current_locale", lambda: "en_US")
    metadata = loader.load_plugin_from_dir(PLUGIN_DIR).metadata
    sources = {
        metadata.name,
        metadata.description,
        metadata.config_fields[0].label,
        metadata.config_fields[0].description,
    }

    for locale in LOCALES:
        path = os.path.join(PLUGIN_DIR, "locale", f"{locale}.json")
        with open(path, encoding="utf-8") as f:
            translations = json.load(f)
        assert set(translations) == sources, locale
        assert all(value.strip() for value in translations.values()), locale
