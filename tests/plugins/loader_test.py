import io
import os
import sys
import textwrap
import zipfile

import pytest

from buzz.plugins import loader
from buzz.plugins.loader import (
    PluginLoadError,
    _find_plugin_root,
    _safe_extract,
    copy_bundled_plugins,
    discover_plugin_dirs,
    download_and_extract,
    ensure_deps_on_path,
    get_plugins_deps_dir,
    get_plugins_dir,
)


VALID_PLUGIN = textwrap.dedent(
    """
    from buzz.plugins.base import BuzzPlugin, PluginMetadata

    class MyPlugin(BuzzPlugin):
        metadata = PluginMetadata(id="my_plugin", name="My Plugin")
    """
)


def _zip_bytes(arcname_to_content: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for arcname, content in arcname_to_content.items():
            zf.writestr(arcname, content)
    return buffer.getvalue()


class TestDirectoryHelpers:
    def test_get_plugins_dir_creates_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "user_cache_dir", lambda _app: str(tmp_path))
        path = get_plugins_dir()
        assert path == str(tmp_path / "plugins")
        assert os.path.isdir(path)

    def test_get_plugins_deps_dir_creates_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(loader, "user_cache_dir", lambda _app: str(tmp_path))
        path = get_plugins_deps_dir()
        assert path == str(tmp_path / "plugins_deps")
        assert os.path.isdir(path)

    def test_ensure_deps_on_path_inserts_once(self, tmp_path, monkeypatch):
        deps = str(tmp_path / "deps")
        os.makedirs(deps)
        monkeypatch.setattr(loader, "get_plugins_deps_dir", lambda: deps)

        original = list(sys.path)
        try:
            ensure_deps_on_path()
            assert sys.path[0] == deps
            ensure_deps_on_path()
            assert sys.path.count(deps) == 1
        finally:
            sys.path[:] = original


class TestCopyBundledPlugins:
    def test_copies_existing_bundled_plugin(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        bundled_root = tmp_path / "bundled"

        monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))
        monkeypatch.setattr(loader, "BUNDLED_PLUGIN_IDS", ["sample"])

        def fake_get_path(rel):
            src = bundled_root / rel
            return str(src)

        monkeypatch.setattr(loader, "get_path", fake_get_path)

        src = bundled_root / "plugins" / "sample"
        src.mkdir(parents=True)
        (src / "plugin.py").write_text(VALID_PLUGIN)

        copy_bundled_plugins()

        assert (plugins_dir / "sample" / "plugin.py").is_file()

    def test_skips_when_destination_exists(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        (plugins_dir / "sample").mkdir(parents=True)

        monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))
        monkeypatch.setattr(loader, "BUNDLED_PLUGIN_IDS", ["sample"])

        called = []
        monkeypatch.setattr(loader, "get_path", lambda rel: called.append(rel) or rel)

        copy_bundled_plugins()
        assert called == []

    def test_warns_when_source_missing(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))
        monkeypatch.setattr(loader, "BUNDLED_PLUGIN_IDS", ["missing"])
        monkeypatch.setattr(
            loader, "get_path", lambda rel: str(tmp_path / "does-not-exist")
        )

        copy_bundled_plugins()
        assert not (plugins_dir / "missing").exists()


class TestDiscoverPluginDirs:
    def test_returns_only_valid_plugin_dirs(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        valid = plugins_dir / "valid"
        valid.mkdir()
        (valid / "plugin.py").write_text(VALID_PLUGIN)

        # A directory without the entry module is ignored.
        (plugins_dir / "empty").mkdir()
        # A plain file is ignored.
        (plugins_dir / "note.txt").write_text("x")

        monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))

        dirs = discover_plugin_dirs()
        assert dirs == [str(valid)]


class TestSafeExtract:
    def test_rejects_path_traversal(self, tmp_path):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../evil.txt", "pwned")

        dest = tmp_path / "dest"
        dest.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            with pytest.raises(PluginLoadError):
                _safe_extract(zf, str(dest))

    def test_extracts_safe_members(self, tmp_path):
        zip_path = tmp_path / "ok.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("plugin.py", VALID_PLUGIN)

        dest = tmp_path / "dest"
        dest.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            _safe_extract(zf, str(dest))

        assert (dest / "plugin.py").is_file()


class TestFindPluginRoot:
    def test_flat_layout(self, tmp_path):
        (tmp_path / "plugin.py").write_text(VALID_PLUGIN)
        assert _find_plugin_root(str(tmp_path)) == str(tmp_path)

    def test_single_nested_folder(self, tmp_path):
        nested = tmp_path / "wrapper"
        nested.mkdir()
        (nested / "plugin.py").write_text(VALID_PLUGIN)
        assert _find_plugin_root(str(tmp_path)) == str(nested)

    def test_raises_when_no_entry_module(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        with pytest.raises(PluginLoadError):
            _find_plugin_root(str(tmp_path))


class TestDownloadAndExtract:
    def test_installs_valid_plugin(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))

        data = _zip_bytes({"plugin.py": VALID_PLUGIN})
        monkeypatch.setattr(loader, "urlopen", lambda *a, **k: io.BytesIO(data))

        plugin_id = download_and_extract("http://example.com/plugin.zip")

        assert plugin_id == "my_plugin"
        assert (plugins_dir / "my_plugin" / "plugin.py").is_file()

    def test_reinstall_replaces_existing(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        existing = plugins_dir / "my_plugin"
        existing.mkdir(parents=True)
        (existing / "stale.txt").write_text("old")
        monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))

        data = _zip_bytes({"plugin.py": VALID_PLUGIN})
        monkeypatch.setattr(loader, "urlopen", lambda *a, **k: io.BytesIO(data))

        download_and_extract("http://example.com/plugin.zip")

        assert not (existing / "stale.txt").exists()
        assert (existing / "plugin.py").is_file()

    def test_bad_zip_raises(self, tmp_path, monkeypatch):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        monkeypatch.setattr(loader, "get_plugins_dir", lambda: str(plugins_dir))
        monkeypatch.setattr(
            loader, "urlopen", lambda *a, **k: io.BytesIO(b"not a zip")
        )

        with pytest.raises(PluginLoadError):
            download_and_extract("http://example.com/plugin.zip")

    def test_download_failure_raises(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr(loader, "urlopen", boom)
        with pytest.raises(PluginLoadError):
            download_and_extract("http://example.com/plugin.zip")
