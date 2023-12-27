from dataclasses import dataclass

from PyQt6.QtCore import QSettings

from buzz.widgets.preferences_dialog.models.folder_watch_preferences import (
    FolderWatchPreferences,
)


@dataclass
class Preferences:
    folder_watch: FolderWatchPreferences

    def save(self, settings: QSettings):
        settings.beginGroup("folder_watch")
        self.folder_watch.save(settings)
        settings.endGroup()

    @classmethod
    def load(cls, settings: QSettings) -> "Preferences":
        settings.beginGroup("folder_watch")
        folder_watch = FolderWatchPreferences.load(settings)
        settings.endGroup()
        return Preferences(folder_watch=folder_watch)
