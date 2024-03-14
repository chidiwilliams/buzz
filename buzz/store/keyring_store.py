import enum
import logging

import keyring

from buzz.settings.settings import APP_NAME


class Key(enum.Enum):
    OPENAI_API_KEY = "OpenAI API key"


def get_password(key: Key) -> str | None:
    try:
        password = keyring.get_password(APP_NAME, username=key.value)
        if password is None:
            return ""
        return password
    except Exception as exc:
        logging.warning("Unable to read from keyring: %s", exc)
        return ""


def set_password(username: Key, password: str) -> None:
    keyring.set_password(APP_NAME, username.value, password)
