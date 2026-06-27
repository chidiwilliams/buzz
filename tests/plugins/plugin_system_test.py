import os
import textwrap

import pytest

from buzz.plugins import loader
from buzz.plugins.loader import PluginLoadError, load_plugin_from_dir
from buzz.plugins.manager import PluginManager
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import Segment


VALID_PLUGIN = textwrap.dedent(
    """
    from buzz.plugins.base import (
        BuzzPlugin, PluginMetadata, ConfigField, ConfigFieldType,
    )

    class MyPlugin(BuzzPlugin):
        metadata = PluginMetadata(
            id="my_plugin",
            name="My Plugin",
            config_fields=[
                ConfigField(key="text", label="Text", default="hello"),
                ConfigField(key="flag", label="Flag",
                            type=ConfigFieldType.BOOL, default=True),
                ConfigField(key="secret", label="Secret",
                            type=ConfigFieldType.PASSWORD),
            ],
        )

        def before_transcription(self, task, context):
            return task.file_path + ".processed"

        def after_transcription(self, task, segments, context):
            return segments + [__import__("buzz.transcriber.transcriber",
                fromlist=["Segment"]).Segment(0, 1, "added")]

        def on_complete(self, transcription_id, task, segments, context):
            context.config["_ran"] = True
    """
)


def _write_plugin(plugin_dir, source=VALID_PLUGIN):
    os.makedirs(plugin_dir, exist_ok=True)
    with open(os.path.join(plugin_dir, "plugin.py"), "w") as f:
        f.write(source)
    return plugin_dir


@pytest.fixture()
def isolated_plugins(tmp_path, monkeypatch):
    """Point the loader at temp dirs and stub keyring + bundled-copy."""
    plugins_dir = tmp_path / "plugins"
    deps_dir = tmp_path / "deps"
    plugins_dir.mkdir()
    deps_dir.mkdir()

    monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))
    monkeypatch.setattr(loader, "get_plugins_deps_dir", lambda: str(deps_dir))
    monkeypatch.setattr(loader, "copy_bundled_plugins", lambda: None)

    secrets = {}
    import buzz.plugins.manager as manager_module

    monkeypatch.setattr(
        manager_module.keyring_store, "get_secret", lambda name: secrets.get(name, "")
    )
    monkeypatch.setattr(
        manager_module.keyring_store,
        "set_secret",
        lambda name, value: secrets.__setitem__(name, value),
    )
    monkeypatch.setattr(
        manager_module.keyring_store,
        "delete_secret",
        lambda name: secrets.pop(name, None),
    )
    return plugins_dir, deps_dir, secrets


@pytest.fixture()
def plugin_settings():
    """An isolated Settings instance so tests don't pollute real QSettings."""
    settings = Settings(application="plugins-test")
    # Don't fall back to the shared org-level settings file.
    settings.settings.setFallbacksEnabled(False)
    settings.settings.clear()
    settings.settings.sync()
    yield settings
    settings.settings.clear()
    settings.settings.sync()


def test_load_valid_plugin(tmp_path):
    plugin_dir = _write_plugin(str(tmp_path / "my_plugin"))
    plugin = load_plugin_from_dir(plugin_dir)
    assert plugin.metadata.id == "my_plugin"
    assert plugin.metadata.name == "My Plugin"


def test_load_invalid_plugin_no_subclass(tmp_path):
    plugin_dir = _write_plugin(str(tmp_path / "bad"), source="x = 1\n")
    with pytest.raises(PluginLoadError):
        load_plugin_from_dir(plugin_dir)


def test_manager_discovers_and_orders(qtbot, isolated_plugins, transcription_service, plugin_settings):
    plugins_dir, _deps, _secrets = isolated_plugins
    _write_plugin(str(plugins_dir / "my_plugin"))

    manager = PluginManager(transcription_service, plugin_settings)
    manager.initialize()

    assert "my_plugin" in manager.plugins
    assert "my_plugin" in manager.order


def test_config_persistence_and_password(qtbot, isolated_plugins, transcription_service, plugin_settings):
    plugins_dir, _deps, secrets = isolated_plugins
    _write_plugin(str(plugins_dir / "my_plugin"))

    manager = PluginManager(transcription_service, plugin_settings)
    manager.initialize()

    # Defaults come through.
    cfg = manager.get_config("my_plugin")
    assert cfg["text"] == "hello"
    assert cfg["flag"] is True

    manager.set_config(
        "my_plugin", {"text": "world", "flag": False, "secret": "s3cr3t"}
    )

    cfg = manager.get_config("my_plugin")
    assert cfg["text"] == "world"
    assert cfg["flag"] is False
    # Password stored via keyring, not QSettings.
    assert cfg["secret"] == "s3cr3t"
    assert secrets["plugin:my_plugin:secret"] == "s3cr3t"

    # Cleanup settings pollution.
    manager.remove("my_plugin")


def test_enable_and_order(qtbot, isolated_plugins, transcription_service, plugin_settings):
    plugins_dir, _deps, _secrets = isolated_plugins
    _write_plugin(str(plugins_dir / "a"))
    _write_plugin(
        str(plugins_dir / "b"),
        source=VALID_PLUGIN.replace('"my_plugin"', '"b_plugin"').replace(
            "MyPlugin", "BPlugin"
        ),
    )

    manager = PluginManager(transcription_service, plugin_settings)
    manager.initialize()

    assert manager.enabled_plugins_in_order() == []

    for pid in manager.order:
        manager.set_enabled(pid, True)
    assert len(manager.enabled_plugins_in_order()) == 2

    first = manager.order[0]
    manager.move(first, 1)
    assert manager.order[1] == first

    for pid in list(manager.plugins.keys()):
        manager.remove(pid)


def test_ai_summary_on_complete_writes_notes(monkeypatch):
    from buzz.plugins.ai_summary import plugin as ai_summary
    from buzz.plugins.base import PluginContext

    captured = {}

    class _Message:
        content = "A short summary."

    class _Choice:
        message = _Message()

    class _Completion:
        choices = [_Choice()]

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, *args, **kwargs):
            return _Completion()

    monkeypatch.setattr(ai_summary, "OpenAI", _FakeClient, raising=False)
    # Patch the import inside _summarize.
    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)

    class _Service:
        def update_transcription_notes(self, tid, notes):
            captured["notes"] = (tid, notes)

    class _Task:
        file_path = "/tmp/a.wav"
        original_file_path = "/tmp/a.wav"

    context = PluginContext(
        config={
            "api_key": "key",
            "api_url": "https://example.com/v1",
            "model": "gpt-4o-mini",
            "prompt": "Summarise",
            "save_to_notes": True,
            "save_to_file": False,
        },
        transcription_service=_Service(),
        settings=None,
        logger=__import__("logging").getLogger("test"),
    )

    plugin = ai_summary.AISummaryPlugin()
    plugin.on_complete("tid-1", _Task(), [Segment(0, 1, "hello world")], context)

    assert captured["notes"] == ("tid-1", "A short summary.")


def test_transcript_resizer_loads():
    from buzz.plugins.loader import load_plugin_from_dir

    plugin = load_plugin_from_dir("buzz/plugins/transcript_resizer")
    assert plugin.metadata.id == "transcript_resizer"
    keys = [f.key for f in plugin.metadata.config_fields]
    assert "merge_by_gap" in keys and "max_length" in keys


def test_transcript_resizer_skips_without_word_timings():
    from buzz.plugins.transcript_resizer import plugin as resizer
    from buzz.plugins.base import PluginContext
    import logging

    replaced = {}

    class _Service:
        def replace_transcription_segments(self, tid, segs):
            replaced["called"] = True

    class _Options:
        word_level_timings = False

    class _Task:
        transcription_options = _Options()
        file_path = "/tmp/a.wav"
        original_file_path = "/tmp/a.wav"

    ctx = PluginContext(
        config={}, transcription_service=_Service(), settings=None,
        logger=logging.getLogger("test"),
    )
    resizer.TranscriptResizerPlugin().on_complete("tid", _Task(), [], ctx)
    assert "called" not in replaced


def test_transcript_resizer_regroups_with_word_timings(tmp_path, monkeypatch):
    from buzz.plugins.transcript_resizer import plugin as resizer
    from buzz.plugins.base import PluginContext
    from buzz.transcriber.transcriber import Segment
    import logging

    # A real (silent) audio file so load_audio succeeds.
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")  # load_audio is mocked, content irrelevant

    captured = {}

    class _DBSeg:
        def __init__(self, text, start, end):
            self.text = text
            self.start_time = start
            self.end_time = end

    class _Service:
        def get_transcription_segments(self, transcription_id):
            return [_DBSeg("Hello.", 0, 100), _DBSeg("World.", 100, 200)]

        def replace_transcription_segments(self, tid, segs):
            captured["segs"] = segs

    class _Options:
        word_level_timings = True
        language = "en"

    class _Task:
        transcription_options = _Options()
        file_path = str(audio)
        original_file_path = str(audio)

    # Mock the heavy audio + stable_whisper machinery.
    import buzz.whisper_audio as wa
    monkeypatch.setattr(wa, "load_audio", lambda path: b"audio")

    class _ResSeg:
        def __init__(self, start, end, text):
            self.start = start
            self.end = end
            self.text = text

    class _Result:
        segments = [_ResSeg(0.0, 2.0, "Hello. World.")]

    import stable_whisper
    monkeypatch.setattr(
        stable_whisper, "transcribe_any",
        lambda func, **kw: (func(kw.get("audio")), _Result())[1],
    )

    ctx = PluginContext(
        config={"merge_by_gap": True, "merge_gap_seconds": "0.2",
                "split_by_max_length": True, "max_length": "42",
                "split_by_punctuation": True, "punctuation": ".?!"},
        transcription_service=_Service(), settings=None,
        logger=logging.getLogger("test"),
    )
    resizer.TranscriptResizerPlugin().on_complete(
        "tid", _Task(), [Segment(0, 100, "Hello.")], ctx
    )

    assert "segs" in captured
    assert len(captured["segs"]) == 1
    assert captured["segs"][0].text == "Hello. World."
    assert captured["segs"][0].start == 0
    assert captured["segs"][0].end == 200  # 2.0s * 100


def test_export_docx_loads():
    from buzz.plugins.loader import load_plugin_from_dir

    plugin = load_plugin_from_dir("buzz/plugins/export_docx")
    assert plugin.metadata.id == "export_docx"
    # The DOCX is built from the standard library; no third-party deps.
    assert plugin.metadata.pip_dependencies == []


def test_export_docx_writes_file(tmp_path):
    import logging
    from buzz.plugins.export_docx import plugin as ed
    from buzz.plugins.base import PluginContext

    class _DBSeg:
        def __init__(self, text, start, end):
            self.text = text
            self.start_time = start
            self.end_time = end

    class _Service:
        def get_transcription_segments(self, transcription_id):
            return [_DBSeg("Hello world.", 0, 1500), _DBSeg("Second part.", 5000, 7000)]

    class _Task:
        file_path = "/tmp/myaudio.wav"
        original_file_path = "/tmp/myaudio.wav"

    ctx = PluginContext(
        config={"output_folder": str(tmp_path), "include_timestamps": False},
        transcription_service=_Service(),
        settings=None,
        logger=logging.getLogger("test"),
    )
    ed.ExportDocxPlugin().on_complete("tid", _Task(), [], ctx)

    out = tmp_path / "myaudio.docx"
    assert out.exists() and out.stat().st_size > 0

    import zipfile

    with zipfile.ZipFile(out) as docx:
        assert "word/document.xml" in docx.namelist()
        document = docx.read("word/document.xml").decode("utf-8")

    assert "myaudio" in document  # heading uses the file stem
    assert "Hello world." in document


def test_plugins_dialog_builds_and_wraps(qtbot):
    from PyQt6.QtCore import Qt
    from buzz.widgets.plugins_dialog.plugins_dialog import PluginsDialog
    from buzz.plugins.base import PluginMetadata

    class _FakePlugin:
        metadata = PluginMetadata(
            id="demo",
            name="Demo Plugin",
            description="A long description " * 20,
        )

    class _FakeManager:
        order = ["demo"]

        def all_plugins_in_order(self):
            return [_FakePlugin()]

        def is_enabled(self, _pid):
            return True

    dialog = PluginsDialog(_FakeManager())
    qtbot.addWidget(dialog)

    assert dialog.list_widget.wordWrap() is True
    assert (
        dialog.list_widget.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert dialog.list_widget.count() == 1
    # Default size is ~50% wider than the original 560px.
    assert dialog.width() >= 800


def test_plugin_gettext_translates(tmp_path, monkeypatch):
    import json

    import buzz.plugins.base as base

    plugin_dir = tmp_path / "p"
    locale_dir = plugin_dir / "locale"
    locale_dir.mkdir(parents=True)
    (locale_dir / "lv_LV.json").write_text(
        json.dumps({"Hello": "Sveiki"}), encoding="utf-8"
    )
    plugin_file = str(plugin_dir / "plugin.py")

    monkeypatch.setattr(base, "_current_locale", lambda: "lv_LV")
    translate = base.plugin_gettext(plugin_file)
    assert translate("Hello") == "Sveiki"
    # Untranslated strings fall through unchanged.
    assert translate("Goodbye") == "Goodbye"


def test_plugin_gettext_falls_back_to_language(tmp_path, monkeypatch):
    import json

    import buzz.plugins.base as base

    plugin_dir = tmp_path / "p"
    locale_dir = plugin_dir / "locale"
    locale_dir.mkdir(parents=True)
    (locale_dir / "lv.json").write_text(
        json.dumps({"Hello": "Sveiki"}), encoding="utf-8"
    )

    monkeypatch.setattr(base, "_current_locale", lambda: "lv_LV")
    translate = base.plugin_gettext(str(plugin_dir / "plugin.py"))
    assert translate("Hello") == "Sveiki"


def test_plugin_gettext_no_locale_dir(tmp_path, monkeypatch):
    import buzz.plugins.base as base

    monkeypatch.setattr(base, "_current_locale", lambda: "lv_LV")
    translate = base.plugin_gettext(str(tmp_path / "plugin.py"))
    assert translate("Anything") == "Anything"


def _eld_plugin():
    from buzz.plugins.enhanced_language_detection import plugin as eld

    return eld.EnhancedLanguageDetectionPlugin()


def _eld_context(config=None):
    import logging
    from buzz.plugins.base import PluginContext

    captured = {}

    class _Service:
        def update_transcription_language(self, tid, language):
            captured["lang"] = (tid, language)

    ctx = PluginContext(
        config=config or {},
        transcription_service=_Service(),
        settings=None,
        logger=logging.getLogger("test"),
    )
    return ctx, captured


class _EldOptions:
    def __init__(self, language):
        self.language = language


class _EldTask:
    def __init__(self, language, file_path="/tmp/a.wav", uid="tid-1"):
        self.transcription_options = _EldOptions(language)
        self.file_path = file_path
        self.uid = uid


def test_enhanced_language_detection_loads():
    plugin = load_plugin_from_dir("buzz/plugins/enhanced_language_detection")
    assert plugin.metadata.id == "enhanced_language_detection"
    keys = [f.key for f in plugin.metadata.config_fields]
    assert "download_tiny_if_missing" in keys


def test_eld_skips_explicit_language(monkeypatch):
    plugin = _eld_plugin()
    ctx, captured = _eld_context()

    # Detection must never be invoked for an explicit, non-default language.
    monkeypatch.setattr(
        plugin, "_resolve_model_path", lambda c: (_ for _ in ()).throw(AssertionError())
    )

    task = _EldTask(language="de")
    plugin.before_transcription(task, ctx)

    assert task.transcription_options.language == "de"
    assert "lang" not in captured


@pytest.mark.parametrize("language", [None, "", "en", "EN"])
def test_eld_detects_when_auto_or_en(monkeypatch, language):
    plugin = _eld_plugin()
    ctx, captured = _eld_context()

    monkeypatch.setattr(plugin, "_resolve_model_path", lambda c: "/fake/model.bin")
    from buzz.transcriber import whisper_cpp

    monkeypatch.setattr(
        whisper_cpp.WhisperCpp, "detect_language", staticmethod(lambda f, m: "fr")
    )

    task = _EldTask(language=language)
    plugin.before_transcription(task, ctx)

    assert task.transcription_options.language == "fr"
    assert captured["lang"] == ("tid-1", "fr")


def test_eld_skips_without_file_path(monkeypatch):
    plugin = _eld_plugin()
    ctx, captured = _eld_context()
    monkeypatch.setattr(
        plugin, "_resolve_model_path", lambda c: (_ for _ in ()).throw(AssertionError())
    )

    task = _EldTask(language=None, file_path=None)
    plugin.before_transcription(task, ctx)

    assert task.transcription_options.language is None
    assert "lang" not in captured


def test_eld_keeps_language_when_no_detection(monkeypatch):
    plugin = _eld_plugin()
    ctx, captured = _eld_context()

    monkeypatch.setattr(plugin, "_resolve_model_path", lambda c: "/fake/model.bin")
    from buzz.transcriber import whisper_cpp

    monkeypatch.setattr(
        whisper_cpp.WhisperCpp, "detect_language", staticmethod(lambda f, m: None)
    )

    task = _EldTask(language=None)
    plugin.before_transcription(task, ctx)

    assert task.transcription_options.language is None
    assert "lang" not in captured


def test_eld_resolve_model_path_picks_largest_skips_custom_lumii(monkeypatch):
    from buzz import model_loader
    from buzz.model_loader import WhisperModelSize

    available = {
        WhisperModelSize.TINY: "/models/tiny.bin",
        WhisperModelSize.SMALL: "/models/small.bin",
        WhisperModelSize.LUMII: "/models/lumii.bin",
        WhisperModelSize.CUSTOM: "/models/custom.bin",
    }

    def fake_path(self):
        return available.get(self.whisper_model_size)

    monkeypatch.setattr(
        model_loader.TranscriptionModel, "get_local_model_path", fake_path
    )

    plugin = _eld_plugin()
    ctx, _ = _eld_context()
    # SMALL outranks TINY; LUMII/CUSTOM are excluded even though available.
    assert plugin._resolve_model_path(ctx) == "/models/small.bin"


def test_eld_resolve_model_path_returns_none_when_download_disabled(monkeypatch):
    from buzz import model_loader

    monkeypatch.setattr(
        model_loader.TranscriptionModel, "get_local_model_path", lambda self: None
    )

    plugin = _eld_plugin()
    ctx, _ = _eld_context(config={"download_tiny_if_missing": False})
    assert plugin._resolve_model_path(ctx) is None


def test_eld_resolve_model_path_downloads_tiny_when_missing(monkeypatch):
    from buzz import model_loader
    from buzz.model_loader import WhisperModelSize

    state = {"downloaded": False}

    def fake_path(self):
        if state["downloaded"] and self.whisper_model_size == WhisperModelSize.TINY:
            return "/models/tiny.bin"
        return None

    class _FakeDownloader:
        def __init__(self, model=None):
            self.model = model

        def run(self):
            state["downloaded"] = True

    monkeypatch.setattr(
        model_loader.TranscriptionModel, "get_local_model_path", fake_path
    )
    monkeypatch.setattr(model_loader, "ModelDownloader", _FakeDownloader)

    plugin = _eld_plugin()
    ctx, _ = _eld_context(config={"download_tiny_if_missing": True})
    assert plugin._resolve_model_path(ctx) == "/models/tiny.bin"
    assert state["downloaded"] is True


def test_before_and_after_hooks(qtbot, isolated_plugins, transcription_service, plugin_settings):
    plugins_dir, _deps, _secrets = isolated_plugins
    _write_plugin(str(plugins_dir / "my_plugin"))

    manager = PluginManager(transcription_service, plugin_settings)
    manager.initialize()
    manager.set_enabled("my_plugin", True)

    class FakeTask:
        file_path = "/tmp/audio.wav"

    task = FakeTask()
    manager.run_before_transcription(task)
    assert task.file_path == "/tmp/audio.wav.processed"

    segments = [Segment(0, 1, "original")]
    result = manager.run_after_transcription(task, segments)
    assert len(result) == 2
    assert result[-1].text == "added"

    manager.remove("my_plugin")


# ---------------------------------------------------------------------------
# skip_already_transcribed plugin tests
# ---------------------------------------------------------------------------

def _sat_plugin():
    from buzz.plugins.skip_already_transcribed import plugin as sat
    return sat.SkipAlreadyTranscribedPlugin()


def _sat_context(config=None, db_records=None):
    import logging
    from buzz.plugins.base import PluginContext

    # db_records: {filename: [db_segment, ...]} where db_segment has .start_time/.end_time/.text
    records = db_records or {}

    class _DBSeg:
        def __init__(self, text, start, end):
            self.text = text
            self.start_time = start
            self.end_time = end

    class _Service:
        def find_completed_transcription_by_filename(self, filename):
            return filename if filename in records else None

        def get_transcription_segments(self, tid):
            return records.get(tid, [])

    ctx = PluginContext(
        config=config or {"check_result_files": True, "check_database": False},
        transcription_service=_Service(),
        settings=None,
        logger=logging.getLogger("test"),
    )
    return ctx


class _SatTask:
    def __init__(self, file_path="/tmp/audio.mp3", output_directory=None):
        self.file_path = file_path
        self.original_file_path = file_path
        self.output_directory = output_directory


def test_skip_already_transcribed_loads():
    from buzz.plugins.loader import load_plugin_from_dir
    plugin = load_plugin_from_dir("buzz/plugins/skip_already_transcribed")
    assert plugin.metadata.id == "skip_already_transcribed"
    keys = [f.key for f in plugin.metadata.config_fields]
    assert "check_result_files" in keys
    assert "check_database" in keys


def test_sat_returns_none_when_no_files_and_db_disabled(tmp_path):
    plugin = _sat_plugin()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    ctx = _sat_context(config={"check_result_files": True, "check_database": False})
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is None


def test_sat_skips_on_txt_file(tmp_path):
    plugin = _sat_plugin()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    txt = tmp_path / "audio (transcribed on 01-Jan-2024 12-00-00).txt"
    txt.write_text("Hello world.", encoding="utf-8")

    ctx = _sat_context(config={"check_result_files": True, "check_database": False})
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is not None
    assert len(result) == 1
    assert result[0].text == "Hello world."
    assert result[0].start == 0
    assert result[0].end == 0


def test_sat_skips_on_srt_file(tmp_path):
    plugin = _sat_plugin()
    audio = tmp_path / "lecture.mp3"
    audio.write_bytes(b"")
    srt = tmp_path / "lecture (transcribed on 01-Jan-2024 12-00-00).srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,500\nHello there.\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nGeneral Kenobi.\n\n",
        encoding="utf-8",
    )

    ctx = _sat_context(config={"check_result_files": True, "check_database": False})
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is not None
    assert len(result) == 2
    assert result[0].text == "Hello there."
    assert result[0].start == 1000
    assert result[0].end == 3500
    assert result[1].text == "General Kenobi."
    assert result[1].start == 4000


def test_sat_skips_on_vtt_file(tmp_path):
    plugin = _sat_plugin()
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"")
    vtt = tmp_path / "talk (transcribed on 01-Jan-2024 12-00-00).vtt"
    vtt.write_text(
        "WEBVTT\n\n"
        "00:00:00.500 --> 00:00:02.000\nFirst line.\n\n"
        "00:00:03.000 --> 00:00:05.000\nSecond line.\n\n",
        encoding="utf-8",
    )

    ctx = _sat_context(config={"check_result_files": True, "check_database": False})
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is not None
    assert len(result) == 2
    assert result[0].text == "First line."
    assert result[0].start == 500
    assert result[1].text == "Second line."
    assert result[1].start == 3000


def test_sat_returns_none_when_result_files_disabled(tmp_path):
    plugin = _sat_plugin()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    (tmp_path / "audio.txt").write_text("Hello world.", encoding="utf-8")

    ctx = _sat_context(config={"check_result_files": False, "check_database": False})
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is None


def test_sat_skips_on_db_record(tmp_path):
    plugin = _sat_plugin()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")

    class _DBSeg:
        def __init__(self, text, start, end):
            self.text = text
            self.start_time = start
            self.end_time = end

    ctx = _sat_context(
        config={"check_result_files": False, "check_database": True},
        db_records={"audio.mp3": [_DBSeg("From DB.", 0, 2000)]},
    )
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is not None
    assert len(result) == 1
    assert result[0].text == "From DB."
    assert result[0].start == 0
    assert result[0].end == 2000


def test_sat_no_skip_when_db_returns_none(tmp_path):
    plugin = _sat_plugin()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")

    ctx = _sat_context(
        config={"check_result_files": False, "check_database": True},
        db_records={},
    )
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is None


def test_sat_result_files_checked_before_db(tmp_path):
    """Result file check wins if both options are enabled."""
    plugin = _sat_plugin()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    (tmp_path / "audio (transcribed on 01-Jan-2024 12-00-00).txt").write_text(
        "From file.", encoding="utf-8"
    )

    class _DBSeg:
        text = "From DB."
        start_time = 0
        end_time = 1000

    ctx = _sat_context(
        config={"check_result_files": True, "check_database": True},
        db_records={"audio.mp3": [_DBSeg()]},
    )
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is not None
    assert result[0].text == "From file."


def test_sat_strips_speech_suffix(tmp_path):
    """Files with _speech suffix (post speech-extraction) match by original stem."""
    plugin = _sat_plugin()
    audio = tmp_path / "audio_speech.mp3"
    audio.write_bytes(b"")
    (tmp_path / "audio (transcribed on 01-Jan-2024 12-00-00).txt").write_text(
        "From file.", encoding="utf-8"
    )

    ctx = _sat_context(config={"check_result_files": True, "check_database": False})
    result = plugin.check_skip(_SatTask(file_path=str(audio)), ctx)
    assert result is not None
    assert result[0].text == "From file."


def test_sat_run_check_skip_integration(qtbot, isolated_plugins, transcription_service, plugin_settings, tmp_path):
    """Manager.run_check_skip calls through to the plugin."""
    from buzz.plugins.manager import PluginManager
    from buzz.plugins import loader

    plugins_dir, _deps, _secrets = isolated_plugins

    import shutil
    sat_src = "buzz/plugins/skip_already_transcribed"
    shutil.copytree(sat_src, str(plugins_dir / "skip_already_transcribed"))

    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")
    (tmp_path / "audio (transcribed on 01-Jan-2024 12-00-00).txt").write_text(
        "Existing transcript.", encoding="utf-8"
    )

    manager = PluginManager(transcription_service, plugin_settings)
    manager.initialize()
    manager.set_enabled("skip_already_transcribed", True)
    manager.set_config("skip_already_transcribed", {"check_result_files": True, "check_database": False})

    task = _SatTask(file_path=str(audio))
    should_skip, segments = manager.run_check_skip(task)

    assert should_skip is True
    assert len(segments) == 1
    assert segments[0].text == "Existing transcript."

    manager.remove("skip_already_transcribed")


# ---------------------------------------------------------------------------
# DeepFilterNet plugin tests
# ---------------------------------------------------------------------------

def _dfn_plugin():
    from buzz.plugins.loader import load_plugin_from_dir
    return load_plugin_from_dir("buzz/plugins/deep_filter_net")


def _dfn_context(config=None):
    import logging
    from buzz.plugins.base import PluginContext
    return PluginContext(
        config=config or {},
        transcription_service=None,
        settings=None,
        logger=logging.getLogger("test"),
    )


class _DfnTask:
    def __init__(self, file_path="/tmp/audio.mp3"):
        self.file_path = file_path
        self.original_file_path = file_path


def test_deep_filter_net_loads():
    plugin = _dfn_plugin()
    assert plugin.metadata.id == "deep_filter_net"
    keys = [f.key for f in plugin.metadata.config_fields]
    assert "keep_denoised_file" in keys


def test_deep_filter_net_before_transcription_creates_denoised_file(tmp_path):
    plugin = _dfn_plugin()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")

    import sys
    from unittest.mock import MagicMock, patch

    mock_audio_tensor = MagicMock()
    mock_sr = MagicMock()
    mock_model = MagicMock()
    mock_df_state = MagicMock()
    mock_df_state.sr.return_value = mock_sr
    mock_enhanced = MagicMock()

    df_module = MagicMock()
    df_module.init_df.return_value = (mock_model, mock_df_state, None)
    df_module.load_audio.return_value = (mock_audio_tensor, mock_sr)
    df_module.enhance.return_value = mock_enhanced

    with patch.dict(sys.modules, {"df": MagicMock(), "df.enhance": df_module}):
        task = _DfnTask(file_path=str(audio))
        result = plugin.before_transcription(task, _dfn_context())

    expected = str(tmp_path / "audio_DeepFilterNet3.wav")
    assert result == expected
    df_module.init_df.assert_called_once()
    df_module.load_audio.assert_called_once_with(str(audio), sr=mock_sr)
    df_module.enhance.assert_called_once_with(mock_model, mock_df_state, mock_audio_tensor)
    df_module.save_audio.assert_called_once_with(expected, mock_enhanced, mock_sr)


def test_deep_filter_net_returns_none_on_error():
    plugin = _dfn_plugin()

    import sys
    from unittest.mock import MagicMock, patch

    df_module = MagicMock()
    df_module.init_df.side_effect = RuntimeError("model not found")

    with patch.dict(sys.modules, {"df": MagicMock(), "df.enhance": df_module}):
        task = _DfnTask(file_path="/tmp/audio.mp3")
        result = plugin.before_transcription(task, _dfn_context())

    assert result is None


def test_deep_filter_net_deletes_file_when_keep_false(tmp_path):
    plugin = _dfn_plugin()
    denoised = tmp_path / "audio_DeepFilterNet3.wav"
    denoised.write_bytes(b"")

    task = _DfnTask(file_path=str(denoised))
    plugin.on_complete(None, task, [], _dfn_context(config={"keep_denoised_file": False}))

    assert not denoised.exists()


def test_deep_filter_net_keeps_file_when_keep_true(tmp_path):
    plugin = _dfn_plugin()
    denoised = tmp_path / "audio_DeepFilterNet3.wav"
    denoised.write_bytes(b"")

    task = _DfnTask(file_path=str(denoised))
    plugin.on_complete(None, task, [], _dfn_context(config={"keep_denoised_file": True}))

    assert denoised.exists()


def test_deep_filter_net_does_not_delete_non_dfn_file(tmp_path):
    plugin = _dfn_plugin()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"")

    task = _DfnTask(file_path=str(audio))
    plugin.on_complete(None, task, [], _dfn_context(config={"keep_denoised_file": False}))

    assert audio.exists()
