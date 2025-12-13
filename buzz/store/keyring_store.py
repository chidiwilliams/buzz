import base64
import enum
import hashlib
import json
import logging
import os
import sys

import keyring

from buzz.settings.settings import APP_NAME


class Key(enum.Enum):
    OPENAI_API_KEY = "OpenAI API key"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _get_secrets_file_path() -> str:
    """Get the path to the local encrypted secrets file."""
    from platformdirs import user_data_dir

    data_dir = user_data_dir(APP_NAME)
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, ".secrets.json")


def _get_portal_secret() -> bytes | None:
    """Get the application secret from XDG Desktop Portal.

    The portal provides a per-application secret that can be used
    for encrypting application-specific data. This works in sandboxed
    environments (Snap/Flatpak) via the desktop plug.
    """
    if not _is_linux():
        return None

    try:
        from jeepney import DBusAddress, new_method_call
        from jeepney.io.blocking import open_dbus_connection
        import socket

        # Open connection with file descriptor support enabled
        conn = open_dbus_connection(bus="SESSION", enable_fds=True)

        portal = DBusAddress(
            "/org/freedesktop/portal/desktop",
            bus_name="org.freedesktop.portal.Desktop",
            interface="org.freedesktop.portal.Secret",
        )

        # Create a socket pair for receiving the secret
        sock_read, sock_write = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

        try:
            # Build the method call with file descriptor
            # RetrieveSecret(fd: h, options: a{sv}) -> (handle: o)
            # Pass the socket object directly - jeepney handles fd passing
            msg = new_method_call(portal, "RetrieveSecret", "ha{sv}", (sock_write, {}))

            # Send message and get reply
            conn.send_and_get_reply(msg, timeout=10)

            # Close the write end - portal has it now
            sock_write.close()
            sock_write = None

            # Read the secret from the read end
            # The portal writes the secret and closes its end
            sock_read.settimeout(5.0)
            secret_data = b""
            while True:
                try:
                    chunk = sock_read.recv(4096)
                    if not chunk:
                        break
                    secret_data += chunk
                except socket.timeout:
                    break

            if secret_data:
                return secret_data

            return None

        finally:
            sock_read.close()
            if sock_write is not None:
                sock_write.close()

    except Exception as exc:
        logging.debug("XDG Portal secret not available: %s", exc)
        return None


def _derive_key(master_secret: bytes, key_name: str) -> bytes:
    """Derive a key-specific encryption key from the master secret."""
    # Use PBKDF2 to derive a key for this specific secret
    return hashlib.pbkdf2_hmac(
        "sha256",
        master_secret,
        f"{APP_NAME}:{key_name}".encode(),
        100000,
        dklen=32,
    )


def _encrypt_value(value: str, key: bytes) -> str:
    """Encrypt a value using XOR with the derived key (simple encryption)."""
    # For a more secure implementation, use cryptography library with AES
    # This is a simple XOR-based encryption suitable for the use case
    value_bytes = value.encode("utf-8")
    key_extended = (key * ((len(value_bytes) // len(key)) + 1))[: len(value_bytes)]
    encrypted = bytes(a ^ b for a, b in zip(value_bytes, key_extended))
    return base64.b64encode(encrypted).decode("ascii")


def _decrypt_value(encrypted: str, key: bytes) -> str:
    """Decrypt a value using XOR with the derived key."""
    encrypted_bytes = base64.b64decode(encrypted.encode("ascii"))
    key_extended = (key * ((len(encrypted_bytes) // len(key)) + 1))[: len(encrypted_bytes)]
    decrypted = bytes(a ^ b for a, b in zip(encrypted_bytes, key_extended))
    return decrypted.decode("utf-8")


def _load_local_secrets() -> dict:
    """Load the local secrets file."""
    secrets_file = _get_secrets_file_path()
    if os.path.exists(secrets_file):
        try:
            with open(secrets_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            logging.debug("Failed to load secrets file: %s", exc)
    return {}


def _save_local_secrets(secrets: dict) -> None:
    """Save secrets to the local file."""
    secrets_file = _get_secrets_file_path()
    try:
        with open(secrets_file, "w") as f:
            json.dump(secrets, f)
        # Set restrictive permissions
        os.chmod(secrets_file, 0o600)
    except IOError as exc:
        logging.warning("Failed to save secrets file: %s", exc)


def _get_portal_password(key: Key) -> str | None:
    """Get a password using the XDG Desktop Portal Secret."""
    portal_secret = _get_portal_secret()
    if portal_secret is None:
        return None

    secrets = _load_local_secrets()
    encrypted_value = secrets.get(key.value)
    if encrypted_value is None:
        return None

    try:
        derived_key = _derive_key(portal_secret, key.value)
        return _decrypt_value(encrypted_value, derived_key)
    except Exception as exc:
        logging.debug("Failed to decrypt portal secret: %s", exc)
        return None


def _set_portal_password(key: Key, password: str) -> bool:
    """Set a password using the XDG Desktop Portal Secret."""
    portal_secret = _get_portal_secret()
    if portal_secret is None:
        return False

    try:
        derived_key = _derive_key(portal_secret, key.value)
        encrypted_value = _encrypt_value(password, derived_key)

        secrets = _load_local_secrets()
        secrets[key.value] = encrypted_value
        _save_local_secrets(secrets)
        return True
    except Exception as exc:
        logging.debug("Failed to set portal secret: %s", exc)
        return False


def _delete_portal_password(key: Key) -> bool:
    """Delete a password from the portal-based local storage."""
    secrets = _load_local_secrets()
    if key.value in secrets:
        del secrets[key.value]
        _save_local_secrets(secrets)
        return True
    return False


def get_password(key: Key) -> str | None:
    # On Linux, try XDG Desktop Portal first (works in sandboxed environments)
    if _is_linux():
        result = _get_portal_password(key)


        if result is not None:
            return result

    # Fall back to keyring (cross-platform, uses Secret Service on Linux)
    try:
        password = keyring.get_password(APP_NAME, username=key.value)
        if password is None:
            return ""
        return password
    except Exception as exc:
        logging.warning("Unable to read from keyring: %s", exc)
        return ""


def set_password(username: Key, password: str) -> None:
    # On Linux, try XDG Desktop Portal first (works in sandboxed environments)
    if _is_linux():
        if _set_portal_password(username, password):
            return

    # Fall back to keyring (cross-platform, uses Secret Service on Linux)
    keyring.set_password(APP_NAME, username.value, password)


def delete_password(key: Key) -> None:
    """Delete a password from the secret store."""
    # On Linux, also delete from portal storage
    if _is_linux():
        _delete_portal_password(key)

    # Delete from keyring
    try:
        keyring.delete_password(APP_NAME, key.value)
    except keyring.errors.PasswordDeleteError:
        pass  # Password doesn't exist, ignore
    except Exception as exc:
        logging.warning("Unable to delete from keyring: %s", exc)
