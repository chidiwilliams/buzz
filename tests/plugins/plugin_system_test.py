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
