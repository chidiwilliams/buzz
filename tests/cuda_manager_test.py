import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from buzz.cuda_manager import (
    CUDA_INDEX_URL,
    CUDA_NVIDIA_PACKAGES_LINUX,
    is_cuda_torch_installed,
    is_flatpak,
    is_nvidia_gpu_present,
    is_snap,
    should_offer_cuda_prompt,
    _cleanup_old_cuda_packages,
    _find_stale_cuda_dirs,
    _get_install_target,
    _get_pip_cmd,
    _get_target_dir,
    _in_virtualenv,
    _pip_install,
    _subprocess_hide_window_kwargs,
    install_cuda,
)


class TestIsSnap:
    def test_returns_true_when_snap_env_set(self, monkeypatch):
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        assert is_snap() is True

    def test_returns_false_when_snap_env_not_set(self, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        assert is_snap() is False


    def test_returns_false_for_an_unrelated_snap(self, monkeypatch):
        # A snap-packaged tool (e.g. snap-installed uv) launching Buzz exports
        # SNAP*, but its user data is not ours to install into.
        monkeypatch.setenv("SNAP", "/snap/astral-uv/1682")
        monkeypatch.setenv("SNAP_NAME", "astral-uv")
        assert is_snap() is False


class TestFindStaleCudaDirs:
    def test_includes_the_target_when_it_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        target = tmp_path / "cuda_packages"
        target.mkdir()
        assert _find_stale_cuda_dirs(target) == [target]

    def test_empty_when_nothing_installed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        assert _find_stale_cuda_dirs(tmp_path / "cuda_packages") == []

    def test_includes_other_snap_revisions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        current = tmp_path / "1682"
        old = tmp_path / "1662"
        for revision in (current, old):
            (revision / "cuda_packages").mkdir(parents=True)
        monkeypatch.setenv("SNAP_USER_DATA", str(current))

        stale = _find_stale_cuda_dirs(current / "cuda_packages")

        assert set(stale) == {current / "cuda_packages", old / "cuda_packages"}

    def test_skips_the_current_symlink(self, tmp_path, monkeypatch):
        # ~/snap/<name>/current symlinks to the active revision; following it
        # would list the same directory twice under two names.
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        revision = tmp_path / "1682"
        (revision / "cuda_packages").mkdir(parents=True)
        (tmp_path / "current").symlink_to(revision)
        monkeypatch.setenv("SNAP_USER_DATA", str(revision))

        assert _find_stale_cuda_dirs(revision / "cuda_packages") == [
            revision / "cuda_packages"
        ]


class TestCleanupOldCudaPackages:
    def test_removes_stale_directory(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        target = tmp_path / "cuda_packages"
        (target / "torch").mkdir(parents=True)

        _cleanup_old_cuda_packages(target)

        assert not target.exists()

    def test_reports_progress(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        target = tmp_path / "cuda_packages"
        target.mkdir()
        messages = []

        _cleanup_old_cuda_packages(target, messages.append)

        assert any("Removing previous CUDA packages" in m for m in messages)

    def test_survives_removal_failure(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        target = tmp_path / "cuda_packages"
        target.mkdir()

        with patch("shutil.rmtree", side_effect=OSError("permission denied")):
            _cleanup_old_cuda_packages(target)  # must not raise

    def test_install_cleans_before_installing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.setenv("FLATPAK_ID", "io.github.chidiwilliams.buzz")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        stale_marker = tmp_path / "buzz" / "cuda_packages" / "torch" / "stale.txt"
        stale_marker.parent.mkdir(parents=True)
        stale_marker.write_text("old install")

        with patch("buzz.cuda_manager._pip_install") as pip_install:
            install_cuda()

        assert not stale_marker.exists()
        assert pip_install.called


class TestIsFlatpak:
    def test_returns_true_when_flatpak_env_set(self, monkeypatch):
        monkeypatch.setenv("FLATPAK_ID", "io.github.chidiwilliams.buzz")
        assert is_flatpak() is True

    def test_returns_false_when_flatpak_env_not_set(self, monkeypatch):
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        assert is_flatpak() is False


class TestShouldOfferCudaPrompt:
    def test_returns_true_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert should_offer_cuda_prompt() is True

    def test_returns_true_on_linux_snap(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        assert should_offer_cuda_prompt() is True

    def test_returns_true_on_linux_flatpak(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.setenv("FLATPAK_ID", "io.github.chidiwilliams.buzz")
        assert should_offer_cuda_prompt() is True

    def test_returns_false_on_linux_bare(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        assert should_offer_cuda_prompt() is False

    def test_returns_false_on_macos(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        assert should_offer_cuda_prompt() is False


class TestIsCudaTorchInstalled:
    def test_returns_true_when_cuda_available(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.__version__ = "2.0.0+cu118"
        mock_torch.version.cuda = "11.8"
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert is_cuda_torch_installed() is True

    def test_returns_false_when_cuda_not_available(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.__version__ = "2.0.0"
        mock_torch.version.cuda = None
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert is_cuda_torch_installed() is False

    def test_returns_false_when_torch_not_installed(self):
        with patch.dict("sys.modules", {"torch": None}):
            with patch("builtins.__import__", side_effect=ImportError):
                assert is_cuda_torch_installed() is False

    def test_logs_warning_when_cuda_compiled_but_unavailable(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.__version__ = "2.0.0+cu118"
        mock_torch.version.cuda = "11.8"
        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch("buzz.cuda_manager.logger") as mock_logger:
                is_cuda_torch_installed()
                mock_logger.warning.assert_called_once()


class TestIsNvidiaGpuPresent:
    def test_returns_true_when_nvidia_smi_succeeds(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert is_nvidia_gpu_present() is True

    def test_falls_back_to_proc_file_when_nvidia_smi_missing(self, tmp_path):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with patch("buzz.cuda_manager.Path") as mock_path_cls:
                mock_path_cls.return_value.exists.return_value = True
                assert is_nvidia_gpu_present() is True

    def test_returns_false_when_nvidia_smi_fails_and_no_proc_file(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            with patch("pathlib.Path.exists", return_value=False):
                assert is_nvidia_gpu_present() is False

    def test_handles_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["nvidia-smi"], 5)):
            with patch("pathlib.Path.exists", return_value=False):
                assert is_nvidia_gpu_present() is False


class TestInVirtualenv:
    def test_returns_true_when_virtual_env_set(self, monkeypatch):
        monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
        assert _in_virtualenv() is True

    def test_returns_true_when_prefix_differs(self, monkeypatch):
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        with patch.object(sys, "prefix", "/some/venv"):
            with patch.object(sys, "base_prefix", "/usr"):
                assert _in_virtualenv() is True

    def test_returns_false_when_no_venv(self, monkeypatch):
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        with patch.object(sys, "prefix", sys.base_prefix):
            assert _in_virtualenv() is False


class TestGetInstallTarget:
    def test_snap_uses_snap_user_data(self, monkeypatch, tmp_path):
        snap_dir = tmp_path / "snap_data"
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        monkeypatch.setenv("SNAP_USER_DATA", str(snap_dir))
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        flags = _get_install_target()
        assert flags[0] == "--target"
        assert "cuda_packages" in flags[1]
        assert str(snap_dir) in flags[1]

    def test_snap_falls_back_to_home_when_no_snap_user_data(self, monkeypatch):
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        with patch("pathlib.Path.mkdir"):
            flags = _get_install_target()
        assert flags[0] == "--target"
        assert "cuda_packages" in flags[1]

    def test_flatpak_uses_xdg_data_home(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.setenv("FLATPAK_ID", "io.github.chidiwilliams.buzz")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        with patch("pathlib.Path.mkdir"):
            flags = _get_install_target()
        assert flags[0] == "--target"
        assert "buzz" in flags[1]
        assert "cuda_packages" in flags[1]

    def test_virtualenv_returns_empty(self, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
        assert _get_install_target() == []

    def test_bare_returns_user_flag(self, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        with patch.object(sys, "prefix", sys.base_prefix):
            assert _get_install_target() == ["--user"]


class TestSubprocessHideWindowKwargs:
    def test_returns_empty_on_linux(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert _subprocess_hide_window_kwargs() == {}

    def test_returns_startupinfo_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        # Only run on actual windows, otherwise mock the STARTUPINFO
        if sys.platform != "win32":
            mock_si = MagicMock()
            with patch("subprocess.STARTUPINFO", return_value=mock_si):
                with patch("subprocess.STARTF_USESHOWWINDOW", 1):
                    with patch("subprocess.SW_HIDE", 0):
                        with patch("subprocess.CREATE_NO_WINDOW", 0x08000000):
                            result = _subprocess_hide_window_kwargs()
            assert "startupinfo" in result
            assert "creationflags" in result


class TestGetPipCmd:
    def test_returns_sys_executable_when_pip_available(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            cmd = _get_pip_cmd()
            assert cmd == [sys.executable, "-m", "pip"]

    def test_bootstraps_pip_when_not_available(self):
        responses = [
            MagicMock(returncode=1),  # pip --version fails
            MagicMock(returncode=0),  # ensurepip succeeds
        ]
        with patch("subprocess.run", side_effect=responses):
            cmd = _get_pip_cmd()
            assert cmd == [sys.executable, "-m", "pip"]

    def test_raises_when_ensurepip_also_fails(self):
        responses = [
            MagicMock(returncode=1),  # pip --version fails
            MagicMock(returncode=1),  # ensurepip fails
        ]
        with patch("subprocess.run", side_effect=responses):
            with pytest.raises(RuntimeError, match="pip is not available"):
                _get_pip_cmd()


class TestPipInstall:
    def test_calls_pip_with_packages(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["Collecting torch\n", "Successfully installed\n"])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with patch("buzz.cuda_manager._get_pip_cmd", return_value=[sys.executable, "-m", "pip"]):
            with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
                _pip_install(["torch==2.0.0"], extra_args=["--index-url", "https://example.com"])

        cmd = mock_popen.call_args[0][0]
        assert "torch==2.0.0" in cmd
        assert "--index-url" in cmd

    def test_raises_on_nonzero_exit(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.returncode = 1
        mock_proc.wait.return_value = None

        with patch("buzz.cuda_manager._get_pip_cmd", return_value=[sys.executable, "-m", "pip"]):
            with patch("subprocess.Popen", return_value=mock_proc):
                with pytest.raises(RuntimeError, match="pip install failed"):
                    _pip_install(["torch==2.0.0"])

    def test_calls_progress_callback(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n"])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        calls = []
        with patch("buzz.cuda_manager._get_pip_cmd", return_value=[sys.executable, "-m", "pip"]):
            with patch("subprocess.Popen", return_value=mock_proc):
                _pip_install(["pkg"], progress_callback=calls.append)

        assert "line1" in calls
        assert "line2" in calls


class TestInstallCuda:
    def test_calls_pip_install_twice(self, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")

        with patch("buzz.cuda_manager._pip_install") as mock_pip:
            install_cuda()

        assert mock_pip.call_count == 2

    def test_passes_progress_callback(self, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")

        messages = []
        with patch("buzz.cuda_manager._pip_install"):
            install_cuda(progress_callback=messages.append)

        assert any("NVIDIA" in m for m in messages)
        assert any("PyTorch" in m for m in messages)

    def test_linux_excludes_linux_only_packages_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)

        captured = []

        def fake_pip(packages, **kwargs):
            captured.append(packages)

        with patch("buzz.cuda_manager._pip_install", side_effect=fake_pip):
            with patch("buzz.cuda_manager._get_install_target", return_value=[]):
                install_cuda()

        nvidia_pkgs = captured[0]
        for pkg in CUDA_NVIDIA_PACKAGES_LINUX:
            assert pkg not in nvidia_pkgs
