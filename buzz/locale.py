import os
import logging
import gettext

from PyQt6.QtCore import QLocale

from buzz.assets import get_path
from buzz.settings.settings import APP_NAME

locale_dir = get_path("locale")
gettext.bindtextdomain("buzz", locale_dir)

custom_locale = os.getenv("BUZZ_LOCALE")

languages = [custom_locale] if custom_locale else QLocale().uiLanguages()

logging.debug(f"UI locales {languages}")

translate = gettext.translation(
    APP_NAME.lower(), locale_dir, languages=languages, fallback=True
)

_ = translate.gettext
