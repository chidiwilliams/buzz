import typing

from buzz.settings.settings import Settings
from buzz.settings.shortcut import Shortcut


class Shortcuts:
    def __init__(self, settings: Settings):
        self.settings = settings

    def get(self, shortcut: Shortcut) -> str:
        custom_shortcuts = self.get_custom_shortcuts()
        return custom_shortcuts.get(shortcut.name, shortcut.sequence)

    def set(self, shortcut: Shortcut, sequence: str) -> None:
        custom_shortcuts = self.get_custom_shortcuts()
        custom_shortcuts[shortcut.name] = sequence
        self.settings.set_value(Settings.Key.SHORTCUTS, custom_shortcuts)

    def clear(self) -> None:
        self.settings.set_value(Settings.Key.SHORTCUTS, {})

    def get_custom_shortcuts(self) -> typing.Dict[str, str]:
        return self.settings.value(Settings.Key.SHORTCUTS, {})
