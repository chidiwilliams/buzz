"""
Central registry and orchestrator for Buzz plugins.

The :class:`PluginManager` loads installed plugins, persists their enabled state,
execution order and configuration, installs declared pip dependencies, and
dispatches the lifecycle hooks at the right points in the transcription pipeline.

A single instance is created by ``MainWindow`` and shared with the transcription
queue worker (for the audio hook) and the Plugins management UI.
"""

import json
import logging
import os
from typing import Dict, List, Optional

from buzz.plugins.base import BuzzPlugin, ConfigFieldType, PluginContext
from buzz.plugins import loader
from buzz.plugins.post_processing import MainThreadInvoker, MainThreadServiceProxy
from buzz.settings.settings import Settings
from buzz.store import keyring_store

logger = logging.getLogger(__name__)

_SETTINGS_GROUP = "plugins"
_INSTALLED_DEPS_FILE = ".installed.json"


def _secret_name(plugin_id: str, field_key: str) -> str:
    return f"plugin:{plugin_id}:{field_key}"


class PluginManager:
    def __init__(self, transcription_service, settings: Optional[Settings] = None):
        self.transcription_service = transcription_service
        self.settings = settings or Settings()
        self.plugins: Dict[str, BuzzPlugin] = {}
        self.order: List[str] = []
        self.enabled: Dict[str, bool] = {}
        # Created on the main thread; used to marshal DB access from background
        # plugin work back to the main thread.
        self._invoker = MainThreadInvoker()
        self._service_proxy = MainThreadServiceProxy(
            transcription_service, self._invoker
        )

    # --- lifecycle -------------------------------------------------------
    def initialize(self) -> None:
        loader.ensure_deps_on_path()
        loader.copy_bundled_plugins()
        self._load_state()
        for path in loader.discover_plugin_dirs():
            try:
                plugin = loader.load_plugin_from_dir(path)
                if plugin.metadata.id in self.plugins:
                    logger.warning(
                        "Duplicate plugin id '%s' at %s, skipping",
                        plugin.metadata.id,
                        path,
                    )
                    continue
                self.plugins[plugin.metadata.id] = plugin
                try:
                    self._install_deps_if_needed(plugin)
                except Exception as exc:
                    logger.warning(
                        "Dependency install failed for plugin '%s': %s",
                        plugin.metadata.id,
                        exc,
                    )
            except Exception as exc:
                logger.warning("Failed to load plugin at %s: %s", path, exc)
        self._reconcile_order()

    # --- ordered iteration ----------------------------------------------
    def enabled_plugins_in_order(self) -> List[BuzzPlugin]:
        result = []
        for plugin_id in self.order:
            plugin = self.plugins.get(plugin_id)
            if plugin is not None and self.enabled.get(plugin_id, False):
                result.append(plugin)
        return result

    def all_plugins_in_order(self) -> List[BuzzPlugin]:
        return [self.plugins[pid] for pid in self.order if pid in self.plugins]

    # --- hook dispatch ---------------------------------------------------
    def run_before_transcription(self, task) -> None:
        for plugin in self.enabled_plugins_in_order():
            try:
                new_path = plugin.before_transcription(task, self._context(plugin))
                if new_path:
                    task.file_path = new_path
            except Exception as exc:
                logger.error(
                    "Plugin '%s' before_transcription failed: %s",
                    plugin.metadata.id,
                    exc,
                    exc_info=True,
                )

    def run_after_transcription(self, task, segments: list) -> list:
        for plugin in self.enabled_plugins_in_order():
            try:
                result = plugin.after_transcription(task, segments, self._context(plugin))
                if result is not None:
                    segments = result
            except Exception as exc:
                logger.error(
                    "Plugin '%s' after_transcription failed: %s",
                    plugin.metadata.id,
                    exc,
                    exc_info=True,
                )
        return segments

    def run_on_complete(self, transcription_id, task, segments: list) -> None:
        for plugin in self.enabled_plugins_in_order():
            try:
                plugin.on_complete(
                    transcription_id, task, segments, self._context(plugin)
                )
            except Exception as exc:
                logger.error(
                    "Plugin '%s' on_complete failed: %s",
                    plugin.metadata.id,
                    exc,
                    exc_info=True,
                )

    def has_enabled_post_hooks(self) -> bool:
        return len(self.enabled_plugins_in_order()) > 0

    def process_completed(self, task, segments: list) -> None:
        """Run the post-transcription pipeline: after_transcription → persist →
        on_complete. Safe to call from a background thread; the database save and
        any DB access from plugins are marshaled to the main thread.
        """
        segments = self.run_after_transcription(task, segments)
        self._invoker.call(
            self.transcription_service.update_transcription_as_completed,
            task.uid,
            segments,
        )
        self.run_on_complete(task.uid, task, segments)

    # --- config ----------------------------------------------------------
    def get_config(self, plugin_id: str) -> dict:
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return {}
        values = {}
        qsettings = self.settings.settings
        qsettings.beginGroup(_SETTINGS_GROUP)
        try:
            for field in plugin.metadata.config_fields:
                if field.type == ConfigFieldType.PASSWORD:
                    stored = keyring_store.get_secret(_secret_name(plugin_id, field.key))
                    values[field.key] = stored if stored else field.default
                elif field.type == ConfigFieldType.BOOL:
                    raw = qsettings.value(
                        f"config/{plugin_id}/{field.key}", field.default
                    )
                    values[field.key] = _coerce_bool(raw)
                else:
                    values[field.key] = qsettings.value(
                        f"config/{plugin_id}/{field.key}", field.default
                    )
        finally:
            qsettings.endGroup()
        return values

    def set_config(self, plugin_id: str, values: dict) -> None:
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return
        qsettings = self.settings.settings
        qsettings.beginGroup(_SETTINGS_GROUP)
        try:
            for field in plugin.metadata.config_fields:
                if field.key not in values:
                    continue
                value = values[field.key]
                if field.type == ConfigFieldType.PASSWORD:
                    keyring_store.set_secret(
                        _secret_name(plugin_id, field.key), value or ""
                    )
                else:
                    qsettings.setValue(f"config/{plugin_id}/{field.key}", value)
        finally:
            qsettings.endGroup()
        qsettings.sync()

    # --- enable / order --------------------------------------------------
    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        self.enabled[plugin_id] = enabled
        self._save_state()

    def is_enabled(self, plugin_id: str) -> bool:
        return self.enabled.get(plugin_id, False)

    def move(self, plugin_id: str, direction: int) -> None:
        """Move a plugin up (direction=-1) or down (direction=+1) in the order."""
        if plugin_id not in self.order:
            return
        index = self.order.index(plugin_id)
        new_index = index + direction
        if new_index < 0 or new_index >= len(self.order):
            return
        self.order[index], self.order[new_index] = (
            self.order[new_index],
            self.order[index],
        )
        self._save_state()

    # --- install / remove ------------------------------------------------
    def add_from_url(self, url: str) -> str:
        """Download, validate and install a plugin from a zip URL. Auto-enables."""
        loader.ensure_deps_on_path()
        plugin_id = loader.download_and_extract(url)
        path = os.path.join(loader.get_plugins_dir(), plugin_id)
        plugin = loader.load_plugin_from_dir(path)
        self.plugins[plugin_id] = plugin
        self._install_deps_if_needed(plugin)
        if plugin_id not in self.order:
            self.order.append(plugin_id)
        self.enabled[plugin_id] = True
        self._save_state()
        return plugin_id

    def remove(self, plugin_id: str) -> None:
        import shutil

        plugin = self.plugins.get(plugin_id)
        # Delete persisted secrets for this plugin's password fields.
        if plugin is not None:
            for field in plugin.metadata.config_fields:
                if field.type == ConfigFieldType.PASSWORD:
                    keyring_store.delete_secret(_secret_name(plugin_id, field.key))

        # Drop the plugin's stored config group.
        qsettings = self.settings.settings
        qsettings.beginGroup(_SETTINGS_GROUP)
        try:
            qsettings.remove(f"config/{plugin_id}")
        finally:
            qsettings.endGroup()

        path = os.path.join(loader.get_plugins_dir(), plugin_id)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        self.plugins.pop(plugin_id, None)
        self.enabled.pop(plugin_id, None)
        if plugin_id in self.order:
            self.order.remove(plugin_id)
        self._save_state()

    # --- dependencies ----------------------------------------------------
    def _install_deps_if_needed(self, plugin: BuzzPlugin) -> None:
        deps = list(plugin.metadata.pip_dependencies or [])
        if not deps:
            return

        deps_dir = loader.get_plugins_deps_dir()
        marker_path = os.path.join(deps_dir, _INSTALLED_DEPS_FILE)
        installed = {}
        if os.path.isfile(marker_path):
            try:
                with open(marker_path) as f:
                    installed = json.load(f)
            except (json.JSONDecodeError, IOError):
                installed = {}

        if installed.get(plugin.metadata.id) == sorted(deps):
            return

        from buzz import pip_utils

        pip_utils.pip_install(deps, extra_args=["--target", deps_dir])

        installed[plugin.metadata.id] = sorted(deps)
        try:
            with open(marker_path, "w") as f:
                json.dump(installed, f)
        except IOError as exc:
            logger.warning("Failed to write deps marker: %s", exc)

    # --- internals -------------------------------------------------------
    def _context(self, plugin: BuzzPlugin) -> PluginContext:
        return PluginContext(
            config=self.get_config(plugin.metadata.id),
            # Marshals DB access to the main thread when called off-thread.
            transcription_service=self._service_proxy,
            settings=self.settings,
            logger=logging.getLogger(f"buzz.plugin.{plugin.metadata.id}"),
        )

    def _load_state(self) -> None:
        qsettings = self.settings.settings
        qsettings.beginGroup(_SETTINGS_GROUP)
        try:
            order = qsettings.value("order", [])
            if isinstance(order, str):
                order = [order] if order else []
            self.order = list(order) if order else []

            self.enabled = {}
            qsettings.beginGroup("enabled")
            try:
                for plugin_id in qsettings.childKeys():
                    self.enabled[plugin_id] = _coerce_bool(qsettings.value(plugin_id))
            finally:
                qsettings.endGroup()
        finally:
            qsettings.endGroup()

    def _save_state(self) -> None:
        qsettings = self.settings.settings
        qsettings.beginGroup(_SETTINGS_GROUP)
        try:
            qsettings.setValue("order", self.order)
            qsettings.remove("enabled")
            qsettings.beginGroup("enabled")
            try:
                for plugin_id, enabled in self.enabled.items():
                    qsettings.setValue(plugin_id, enabled)
            finally:
                qsettings.endGroup()
        finally:
            qsettings.endGroup()
        qsettings.sync()

    def _reconcile_order(self) -> None:
        """Ensure order contains exactly the loaded plugins, preserving sequence."""
        # Drop ids whose plugin failed to load / was removed.
        self.order = [pid for pid in self.order if pid in self.plugins]
        # Append newly discovered plugins not yet in the order.
        for plugin_id in self.plugins:
            if plugin_id not in self.order:
                self.order.append(plugin_id)
        self._save_state()


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
