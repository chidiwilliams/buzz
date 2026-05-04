from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from buzz.widgets.cuda_installer_widget import CudaInstallerDialog, _InstallWorker


class TestInstallWorker:
    def test_calls_install_cuda_and_emits_finished(self):
        worker = _InstallWorker()
        finished_mock = MagicMock()
        worker.signals.finished.connect(finished_mock)

        with patch("buzz.cuda_manager.install_cuda") as mock_install:
            worker.run()

        mock_install.assert_called_once()
        finished_mock.assert_called_once()

    def test_emits_error_on_exception(self):
        worker = _InstallWorker()
        error_mock = MagicMock()
        worker.signals.error.connect(error_mock)

        with patch("buzz.cuda_manager.install_cuda", side_effect=RuntimeError("fail")):
            worker.run()

        error_mock.assert_called_once_with("fail")

    def test_passes_progress_callback_to_install(self):
        worker = _InstallWorker()
        progress_mock = MagicMock()
        worker.signals.progress.connect(progress_mock)

        def fake_install(progress_callback=None):
            if progress_callback:
                progress_callback("installing...")

        with patch("buzz.cuda_manager.install_cuda", side_effect=fake_install):
            worker.run()

        progress_mock.assert_called_once_with("installing...")


class TestCudaInstallerDialog:
    def test_dialog_creates_with_correct_title(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        assert "GPU" in dialog.windowTitle() or "Nvidia" in dialog.windowTitle()

    def test_install_button_exists(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        assert dialog.install_button is not None
        assert dialog.install_button.isEnabled()

    def test_decline_button_exists(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        assert dialog.decline_button is not None

    def test_progress_bar_hidden_initially(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        assert not dialog.progress_bar.isVisible()

    def test_log_view_hidden_initially(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        assert not dialog.log_view.isVisible()

    def test_install_click_shows_progress_bar(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        dialog.show()

        with patch("buzz.widgets.cuda_installer_widget.QThreadPool"):
            dialog._on_install_clicked()

        assert dialog.progress_bar.isVisible()
        assert dialog.log_view.isVisible()
        assert not dialog.install_button.isEnabled()
        assert not dialog.decline_button.isEnabled()

    def test_on_progress_appends_to_log(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        dialog._on_progress("step 1")
        assert "step 1" in dialog.log_view.toPlainText()

    def test_on_finished_re_enables_install_button(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        dialog.install_button.setEnabled(False)
        dialog._on_finished()
        assert dialog.install_button.isEnabled()

    def test_on_finished_hides_progress_bar(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        dialog.progress_bar.setVisible(True)
        dialog._on_finished()
        assert not dialog.progress_bar.isVisible()

    def test_on_finished_shows_completion_message(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        dialog._on_finished()
        assert "complete" in dialog.status_label.text().lower() or "restart" in dialog.status_label.text().lower()

    def test_on_error_shows_error_message(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        dialog._on_error("something went wrong")
        assert "something went wrong" in dialog.status_label.text()

    def test_on_error_re_enables_buttons(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        dialog.install_button.setEnabled(False)
        dialog.decline_button.setEnabled(False)
        dialog._on_error("fail")
        assert dialog.install_button.isEnabled()
        assert dialog.decline_button.isEnabled()

    def test_on_error_hides_progress_bar(self, qtbot: QtBot):
        dialog = CudaInstallerDialog()
        qtbot.add_widget(dialog)
        dialog.progress_bar.setVisible(True)
        dialog._on_error("fail")
        assert not dialog.progress_bar.isVisible()
