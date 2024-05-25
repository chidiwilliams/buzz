import logging

logging
import gettext

from PyQt6.QtCore import QLocale

from buzz.assets import get_path
from buzz.settings.settings import APP_NAME

locale_dir = get_path("locale")
gettext.bindtextdomain("buzz", locale_dir)

logging.debug(f"============= UI LANGUAGES {QLocale().uiLanguages()}")

translate = gettext.translation(
    APP_NAME.lower(), locale_dir, languages=QLocale().uiLanguages(), fallback=True
)

_ = translate.gettext
