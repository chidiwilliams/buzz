import os
from unittest.mock import patch
from buzz.buzz import main

class TestMain:
    def test_main(self):
        with patch('buzz.widgets.application.Application') as mock_application, \
             patch('buzz.cli.parse_command_line') as mock_parse_command_line, \
             patch('buzz.buzz.sys') as mock_sys, \
             patch('buzz.buzz.user_log_dir', return_value='/tmp/buzz') as mock_log_dir:

            mock_application.return_value.exec.return_value = 0

            mock_sys.argv = ['buzz.py']

            main()

            mock_application.assert_called_once_with(mock_sys.argv)
            mock_parse_command_line.assert_called_once_with(mock_application.return_value)
            mock_application.return_value.exec.assert_called_once()
            assert os.path.isdir(mock_log_dir.return_value), "Log dir was not created"
