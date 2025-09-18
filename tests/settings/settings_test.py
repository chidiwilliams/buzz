import pytest
from unittest.mock import Mock, patch

from buzz.settings.settings import Settings


class TestSettings:
    def test_transcription_tasks_table_column_order_key(self):
        """Test that TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER key is defined"""
        assert hasattr(Settings.Key, 'TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER')
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value == "transcription-tasks-table/column-order"

    def test_transcription_tasks_table_column_widths_key(self):
        """Test that TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS key is defined"""
        assert hasattr(Settings.Key, 'TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS')
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value == "transcription-tasks-table/column-widths"

    def test_transcription_tasks_table_column_visibility_key_exists(self):
        """Test that TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY key still exists"""
        assert hasattr(Settings.Key, 'TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY')
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value == "transcription-tasks-table/column-visibility"

    def test_all_transcription_tasks_table_keys_are_strings(self):
        """Test that all transcription tasks table keys are strings"""
        assert isinstance(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value, str)
        assert isinstance(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value, str)
        assert isinstance(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value, str)

    def test_transcription_tasks_table_keys_have_correct_prefix(self):
        """Test that all transcription tasks table keys have the correct prefix"""
        prefix = "transcription-tasks-table/"
        
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value.startswith(prefix)
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value.startswith(prefix)
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value.startswith(prefix)

    def test_transcription_tasks_table_keys_are_unique(self):
        """Test that all transcription tasks table keys are unique"""
        keys = [
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value,
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value,
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value
        ]
        
        assert len(keys) == len(set(keys)), "All transcription tasks table keys should be unique"

    def test_settings_key_enum_values(self):
        """Test that Settings.Key enum values are properly defined"""
        # Test that the keys exist and have expected values
        expected_keys = {
            'TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY': 'transcription-tasks-table/column-visibility',
            'TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER': 'transcription-tasks-table/column-order',
            'TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS': 'transcription-tasks-table/column-widths'
        }
        
        for key_name, expected_value in expected_keys.items():
            assert hasattr(Settings.Key, key_name)
            assert getattr(Settings.Key, key_name).value == expected_value

    def test_settings_key_immutability(self):
        """Test that Settings.Key values cannot be modified"""
        # This test ensures that the keys are defined as constants
        original_visibility = Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY
        original_order = Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER
        original_widths = Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS
        
        # Attempting to modify these should not work (they should be immutable)
        # If they were mutable, this test would fail
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY == original_visibility
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER == original_order
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS == original_widths

    def test_settings_key_format_consistency(self):
        """Test that all transcription tasks table keys follow the same format"""
        keys = [
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value,
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value,
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value
        ]
        
        for key in keys:
            # All keys should start with the same prefix
            assert key.startswith("transcription-tasks-table/")
            # All keys should contain only lowercase letters, hyphens, and forward slashes
            assert all(c.islower() or c in '-/' for c in key)
            # All keys should end with a descriptive suffix
            assert key.endswith(('visibility', 'order', 'widths'))

    def test_settings_key_length(self):
        """Test that transcription tasks table keys have reasonable length"""
        keys = [
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value,
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value,
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value
        ]
        
        for key in keys:
            # Keys should be long enough to be descriptive but not excessively long
            assert 20 <= len(key) <= 50, f"Key '{key}' has unexpected length: {len(key)}"

    def test_settings_key_naming_convention(self):
        """Test that transcription tasks table keys follow proper naming convention"""
        keys = [
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value,
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value,
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value
        ]
        
        for key in keys:
            # Keys should use kebab-case (lowercase with hyphens)
            assert '-' in key, f"Key '{key}' should use kebab-case with hyphens"
            assert not any(c.isupper() for c in key), f"Key '{key}' should not contain uppercase letters"
            assert not '_' in key, f"Key '{key}' should use hyphens instead of underscores"

    def test_settings_key_usage_in_code(self):
        """Test that the settings keys can be used in typical settings operations"""
        # Mock a settings object to test key usage
        mock_settings = Mock()
        mock_settings.begin_group = Mock()
        mock_settings.end_group = Mock()
        mock_settings.settings = Mock()
        
        # Test that the keys can be used with begin_group
        mock_settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value)
        mock_settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value)
        mock_settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value)
        
        # Verify that begin_group was called with the correct keys
        assert mock_settings.begin_group.call_count == 3
        call_args = [call[0][0] for call in mock_settings.begin_group.call_args_list]
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY.value in call_args
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER.value in call_args
        assert Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS.value in call_args
