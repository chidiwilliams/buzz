import gettext

from PyQt6.QtCore import QLocale

from buzz.assets import get_asset_path
from buzz.settings.settings import APP_NAME

locale_dir = get_asset_path("locale")
gettext.bindtextdomain("buzz", locale_dir)

translate = gettext.translation(
    APP_NAME, locale_dir, languages=QLocale().uiLanguages(), fallback=True
)

_ = translate.gettext
