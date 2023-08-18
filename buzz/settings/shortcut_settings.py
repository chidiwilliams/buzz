import typing

from buzz.settings.settings import Settings
from buzz.settings.shortcut import Shortcut


class ShortcutSettings:
    def __init__(self, settings: Settings):
        self.settings = settings

    def load(self) -> typing.Dict[str, str]:
        shortcuts = Shortcut.get_default_shortcuts()
        custom_shortcuts: typing.Dict[str, str] = self.settings.value(
            Settings.Key.SHORTCUTS, {}
        )
        for shortcut_name in custom_shortcuts:
            shortcuts[shortcut_name] = custom_shortcuts[shortcut_name]
        return shortcuts

    def save(self, shortcuts: typing.Dict[str, str]) -> None:
        self.settings.set_value(Settings.Key.SHORTCUTS, shortcuts)
