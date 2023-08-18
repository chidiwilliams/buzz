import gettext
import os

from PyQt6.QtCore import QLocale

from buzz.assets import get_asset_path
from buzz.settings.settings import APP_NAME

if "LANG" not in os.environ:
    language = str(QLocale().uiLanguages()[0]).replace("-", "_")
    os.environ["LANG"] = language

locale_dir = get_asset_path("locale")
gettext.bindtextdomain("buzz", locale_dir)

translate = gettext.translation(APP_NAME, locale_dir, fallback=True)

_ = translate.gettext
