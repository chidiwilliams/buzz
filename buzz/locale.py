import os
import logging
import gettext

from PyQt6.QtCore import QLocale

from buzz.assets import get_path
from buzz.settings.settings import APP_NAME, Settings

locale_dir = get_path("locale")
gettext.bindtextdomain("buzz", locale_dir)

settings = Settings()

languages = [
    settings.value(settings.Key.UI_LOCALE, QLocale().name())
]

translate = gettext.translation(
    APP_NAME.lower(), locale_dir, languages=languages, fallback=True
)

_ = translate.gettext