import json
import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock

import pytest

from buzz.store.keyring_store import (
    Key,
    _is_linux,
    _derive_key,
    _encrypt_value,
    _decrypt_value,
    _load_local_secrets,
    _save_local_secrets,
    _get_portal_password,
    _set_portal_password,
    _delete_portal_password,
    get_password,
    set_password,
    delete_password,
)
from buzz.settings.settings import APP_NAME


class TestKey:
    def test_openai_api_key_exists(self):
        assert hasattr(Key, "OPENAI_API_KEY")

    def test_openai_api_key_value(self):
        assert Key.OPENAI_API_KEY.value == "OpenAI API key"

    def test_key_is_enum(self):
        assert isinstance(Key.OPENAI_API_KEY, Key)


class TestIsLinux:
    @patch("buzz.store.keyring_store.sys.platform", "linux")
    def test_returns_true_on_linux(self):
        assert _is_linux() is True

    @patch("buzz.store.keyring_store.sys.platform", "linux2")
    def test_returns_true_on_linux2(self):
        assert _is_linux() is True

    @patch("buzz.store.keyring_store.sys.platform", "darwin")
    def test_returns_false_on_macos(self):
        assert _is_linux() is False

    @patch("buzz.store.keyring_store.sys.platform", "win32")
    def test_returns_false_on_windows(self):
        assert _is_linux() is False


class TestDeriveKey:
    def test_derive_key_returns_32_bytes(self):
        master_secret = b"test_secret"
        key_name = "test_key"
        derived = _derive_key(master_secret, key_name)
        assert len(derived) == 32

    def test_derive_key_is_deterministic(self):
        master_secret = b"test_secret"
        key_name = "test_key"
        derived1 = _derive_key(master_secret, key_name)
        derived2 = _derive_key(master_secret, key_name)
        assert derived1 == derived2

    def test_derive_key_different_for_different_names(self):
        master_secret = b"test_secret"
        derived1 = _derive_key(master_secret, "key1")
        derived2 = _derive_key(master_secret, "key2")
        assert derived1 != derived2

    def test_derive_key_different_for_different_secrets(self):
        key_name = "test_key"
        derived1 = _derive_key(b"secret1", key_name)
        derived2 = _derive_key(b"secret2", key_name)
        assert derived1 != derived2


class TestEncryptDecrypt:
    def test_encrypt_decrypt_roundtrip(self):
        key = b"0123456789abcdef0123456789abcdef"  # 32 bytes
        original = "test_password_123"
        encrypted = _encrypt_value(original, key)
        decrypted = _decrypt_value(encrypted, key)
        assert decrypted == original

    def test_encrypt_decrypt_empty_string(self):
        key = b"0123456789abcdef0123456789abcdef"
        original = ""
        encrypted = _encrypt_value(original, key)
        decrypted = _decrypt_value(encrypted, key)
        assert decrypted == original

    def test_encrypt_decrypt_unicode(self):
        key = b"0123456789abcdef0123456789abcdef"
        original = "test_password_\u4e2d\u6587_\U0001f600"
        encrypted = _encrypt_value(original, key)
        decrypted = _decrypt_value(encrypted, key)
        assert decrypted == original

    def test_encrypt_decrypt_long_string(self):
        key = b"0123456789abcdef0123456789abcdef"
        original = "a" * 1000
        encrypted = _encrypt_value(original, key)
        decrypted = _decrypt_value(encrypted, key)
        assert decrypted == original

    def test_encrypted_is_base64(self):
        key = b"0123456789abcdef0123456789abcdef"
        original = "test"
        encrypted = _encrypt_value(original, key)
        # Should be valid base64
        import base64
        base64.b64decode(encrypted)  # Should not raise

    def test_different_keys_produce_different_ciphertext(self):
        key1 = b"0123456789abcdef0123456789abcdef"
        key2 = b"fedcba9876543210fedcba9876543210"
        original = "test_password"
        encrypted1 = _encrypt_value(original, key1)
        encrypted2 = _encrypt_value(original, key2)
        assert encrypted1 != encrypted2


class TestLocalSecrets:
    def test_load_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "buzz.store.keyring_store._get_secrets_file_path",
                return_value=os.path.join(tmpdir, ".secrets.json"),
            ):
                result = _load_local_secrets()
                assert result == {}

    def test_save_and_load_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_path = os.path.join(tmpdir, ".secrets.json")
            with patch(
                "buzz.store.keyring_store._get_secrets_file_path",
                return_value=secrets_path,
            ):
                test_secrets = {"key1": "value1", "key2": "value2"}
                _save_local_secrets(test_secrets)
                loaded = _load_local_secrets()
                assert loaded == test_secrets

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix file permissions not applicable on Windows")
    def test_save_sets_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_path = os.path.join(tmpdir, ".secrets.json")
            with patch(
                "buzz.store.keyring_store._get_secrets_file_path",
                return_value=secrets_path,
            ):
                _save_local_secrets({"key": "value"})
                # Check file permissions (0o600 = owner read/write only)
                mode = os.stat(secrets_path).st_mode & 0o777
                assert mode == 0o600

    def test_load_handles_corrupted_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_path = os.path.join(tmpdir, ".secrets.json")
            with open(secrets_path, "w") as f:
                f.write("not valid json {{{")
            with patch(
                "buzz.store.keyring_store._get_secrets_file_path",
                return_value=secrets_path,
            ):
                result = _load_local_secrets()
                assert result == {}


class TestPortalPassword:
    @patch("buzz.store.keyring_store._get_portal_secret")
    @patch("buzz.store.keyring_store._load_local_secrets")
    def test_get_portal_password_returns_none_when_no_portal(
        self, mock_load, mock_portal
    ):
        mock_portal.return_value = None
        result = _get_portal_password(Key.OPENAI_API_KEY)
        assert result is None

    @patch("buzz.store.keyring_store._get_portal_secret")
    @patch("buzz.store.keyring_store._load_local_secrets")
    def test_get_portal_password_returns_none_when_key_not_found(
        self, mock_load, mock_portal
    ):
        mock_portal.return_value = b"test_secret_64_bytes_" + b"x" * 43
        mock_load.return_value = {}
        result = _get_portal_password(Key.OPENAI_API_KEY)
        assert result is None

    @patch("buzz.store.keyring_store._get_portal_secret")
    @patch("buzz.store.keyring_store._load_local_secrets")
    def test_get_portal_password_decrypts_stored_value(self, mock_load, mock_portal):
        portal_secret = b"test_secret_64_bytes_" + b"x" * 43
        mock_portal.return_value = portal_secret

        # Pre-encrypt a value
        derived_key = _derive_key(portal_secret, Key.OPENAI_API_KEY.value)
        encrypted = _encrypt_value("my_api_key", derived_key)

        mock_load.return_value = {Key.OPENAI_API_KEY.value: encrypted}

        result = _get_portal_password(Key.OPENAI_API_KEY)
        assert result == "my_api_key"

    @patch("buzz.store.keyring_store._get_portal_secret")
    def test_set_portal_password_returns_false_when_no_portal(self, mock_portal):
        mock_portal.return_value = None
        result = _set_portal_password(Key.OPENAI_API_KEY, "test_password")
        assert result is False

    @patch("buzz.store.keyring_store._get_portal_secret")
    @patch("buzz.store.keyring_store._load_local_secrets")
    @patch("buzz.store.keyring_store._save_local_secrets")
    def test_set_portal_password_encrypts_and_saves(
        self, mock_save, mock_load, mock_portal
    ):
        portal_secret = b"test_secret_64_bytes_" + b"x" * 43
        mock_portal.return_value = portal_secret
        mock_load.return_value = {}

        result = _set_portal_password(Key.OPENAI_API_KEY, "test_password")

        assert result is True
        mock_save.assert_called_once()
        saved_secrets = mock_save.call_args[0][0]
        assert Key.OPENAI_API_KEY.value in saved_secrets

        # Verify the saved value can be decrypted
        derived_key = _derive_key(portal_secret, Key.OPENAI_API_KEY.value)
        decrypted = _decrypt_value(saved_secrets[Key.OPENAI_API_KEY.value], derived_key)
        assert decrypted == "test_password"


class TestDeletePortalPassword:
    @patch("buzz.store.keyring_store._load_local_secrets")
    @patch("buzz.store.keyring_store._save_local_secrets")
    def test_delete_existing_key(self, mock_save, mock_load):
        mock_load.return_value = {Key.OPENAI_API_KEY.value: "encrypted_value"}

        result = _delete_portal_password(Key.OPENAI_API_KEY)

        assert result is True
        mock_save.assert_called_once()
        saved_secrets = mock_save.call_args[0][0]
        assert Key.OPENAI_API_KEY.value not in saved_secrets

    @patch("buzz.store.keyring_store._load_local_secrets")
    @patch("buzz.store.keyring_store._save_local_secrets")
    def test_delete_nonexistent_key(self, mock_save, mock_load):
        mock_load.return_value = {}

        result = _delete_portal_password(Key.OPENAI_API_KEY)

        assert result is False
        mock_save.assert_not_called()


class TestGetPassword:
    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store._get_portal_password")
    @patch("buzz.store.keyring_store.keyring")
    def test_returns_portal_password_on_linux(
        self, mock_keyring, mock_portal, mock_is_linux
    ):
        mock_is_linux.return_value = True
        mock_portal.return_value = "portal_password"

        result = get_password(Key.OPENAI_API_KEY)

        assert result == "portal_password"
        mock_keyring.get_password.assert_not_called()

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store._get_portal_password")
    @patch("buzz.store.keyring_store.keyring")
    def test_falls_back_to_keyring_when_portal_returns_none(
        self, mock_keyring, mock_portal, mock_is_linux
    ):
        mock_is_linux.return_value = True
        mock_portal.return_value = None
        mock_keyring.get_password.return_value = "keyring_password"

        result = get_password(Key.OPENAI_API_KEY)

        assert result == "keyring_password"
        mock_keyring.get_password.assert_called_once_with(
            APP_NAME, username=Key.OPENAI_API_KEY.value
        )

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store.keyring")
    def test_uses_keyring_directly_on_non_linux(self, mock_keyring, mock_is_linux):
        mock_is_linux.return_value = False
        mock_keyring.get_password.return_value = "keyring_password"

        result = get_password(Key.OPENAI_API_KEY)

        assert result == "keyring_password"

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store.keyring")
    def test_returns_empty_string_when_keyring_returns_none(
        self, mock_keyring, mock_is_linux
    ):
        mock_is_linux.return_value = False
        mock_keyring.get_password.return_value = None

        result = get_password(Key.OPENAI_API_KEY)

        assert result == ""

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store.keyring")
    def test_returns_empty_string_on_keyring_exception(
        self, mock_keyring, mock_is_linux
    ):
        mock_is_linux.return_value = False
        mock_keyring.get_password.side_effect = Exception("Keyring error")

        result = get_password(Key.OPENAI_API_KEY)

        assert result == ""


class TestSetPassword:
    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store._set_portal_password")
    @patch("buzz.store.keyring_store.keyring")
    def test_uses_portal_on_linux_when_successful(
        self, mock_keyring, mock_portal, mock_is_linux
    ):
        mock_is_linux.return_value = True
        mock_portal.return_value = True

        set_password(Key.OPENAI_API_KEY, "test_password")

        mock_portal.assert_called_once_with(Key.OPENAI_API_KEY, "test_password")
        mock_keyring.set_password.assert_not_called()

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store._set_portal_password")
    @patch("buzz.store.keyring_store.keyring")
    def test_falls_back_to_keyring_when_portal_fails(
        self, mock_keyring, mock_portal, mock_is_linux
    ):
        mock_is_linux.return_value = True
        mock_portal.return_value = False

        set_password(Key.OPENAI_API_KEY, "test_password")

        mock_keyring.set_password.assert_called_once_with(
            APP_NAME, Key.OPENAI_API_KEY.value, "test_password"
        )

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store.keyring")
    def test_uses_keyring_directly_on_non_linux(self, mock_keyring, mock_is_linux):
        mock_is_linux.return_value = False

        set_password(Key.OPENAI_API_KEY, "test_password")

        mock_keyring.set_password.assert_called_once_with(
            APP_NAME, Key.OPENAI_API_KEY.value, "test_password"
        )


class TestDeletePassword:
    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store._delete_portal_password")
    @patch("buzz.store.keyring_store.keyring")
    def test_deletes_from_both_on_linux(
        self, mock_keyring, mock_delete_portal, mock_is_linux
    ):
        mock_is_linux.return_value = True
        mock_delete_portal.return_value = True

        delete_password(Key.OPENAI_API_KEY)

        mock_delete_portal.assert_called_once_with(Key.OPENAI_API_KEY)
        mock_keyring.delete_password.assert_called_once_with(
            APP_NAME, Key.OPENAI_API_KEY.value
        )

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store.keyring")
    def test_deletes_from_keyring_only_on_non_linux(self, mock_keyring, mock_is_linux):
        mock_is_linux.return_value = False

        delete_password(Key.OPENAI_API_KEY)

        mock_keyring.delete_password.assert_called_once_with(
            APP_NAME, Key.OPENAI_API_KEY.value
        )

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store.keyring")
    def test_ignores_password_delete_error(self, mock_keyring, mock_is_linux):
        mock_is_linux.return_value = False
        mock_keyring.errors.PasswordDeleteError = Exception
        mock_keyring.delete_password.side_effect = (
            mock_keyring.errors.PasswordDeleteError("Not found")
        )

        # Should not raise
        delete_password(Key.OPENAI_API_KEY)

    @patch("buzz.store.keyring_store._is_linux")
    @patch("buzz.store.keyring_store.keyring")
    def test_handles_other_keyring_exceptions(self, mock_keyring, mock_is_linux):
        mock_is_linux.return_value = False
        mock_keyring.errors.PasswordDeleteError = KeyError  # Different exception type
        mock_keyring.delete_password.side_effect = RuntimeError("Some other error")

        # Should not raise
        delete_password(Key.OPENAI_API_KEY)


class TestIntegration:
    """Integration tests that test the full flow with mocked portal."""

    @patch("buzz.store.keyring_store._get_portal_secret")
    def test_full_roundtrip_with_portal(self, mock_portal):
        """Test set -> get -> delete flow with portal."""
        portal_secret = b"integration_test_secret_" + b"y" * 40

        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_path = os.path.join(tmpdir, ".secrets.json")

            with patch(
                "buzz.store.keyring_store._get_secrets_file_path",
                return_value=secrets_path,
            ):
                with patch("buzz.store.keyring_store._is_linux", return_value=True):
                    mock_portal.return_value = portal_secret

                    # Set password
                    result = _set_portal_password(Key.OPENAI_API_KEY, "my_secret_key")
                    assert result is True

                    # Get password
                    retrieved = _get_portal_password(Key.OPENAI_API_KEY)
                    assert retrieved == "my_secret_key"

                    # Delete password
                    deleted = _delete_portal_password(Key.OPENAI_API_KEY)
                    assert deleted is True

                    # Verify it's gone
                    retrieved_after_delete = _get_portal_password(Key.OPENAI_API_KEY)
                    assert retrieved_after_delete is None
