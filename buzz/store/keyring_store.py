import enum
import logging

import keyring
from keyring.errors import KeyringLocked, KeyringError, PasswordSetError

from buzz.settings.settings import APP_NAME


class KeyringStore:
    class Key(enum.Enum):
        OPENAI_API_KEY = "OpenAI API key"

    def get_password(self, key: Key) -> str:
        try:
            password = keyring.get_password(APP_NAME, username=key.value)
            if password is None:
                return ""
            return password
        except (KeyringLocked, KeyringError) as exc:
            logging.error("Unable to read from keyring: %s", exc)
            return ""

    def set_password(self, username: Key, password: str) -> None:
        try:
            keyring.set_password(APP_NAME, username.value, password)
        except (KeyringLocked, PasswordSetError) as exc:
            logging.error("Unable to write to keyring: %s", exc)
