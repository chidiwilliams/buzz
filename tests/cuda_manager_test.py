import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from buzz.cuda_manager import (
    CUDA_INDEX_URL,
    CUDA_NVIDIA_PACKAGES_LINUX,
    get_cuda_env_dir,
    get_cuda_env_site_packages,
    get_cuda_root_dir,
    is_cuda_torch_installed,
    is_flatpak,
    is_nvidia_gpu_present,
    is_snap,
    should_offer_cuda_prompt,
    _cleanup_old_cuda_packages,
    _create_cuda_env,
    _find_stale_cuda_dirs,
    _find_uv,
    _get_base_python,
    _run_install,
    _subprocess_hide_window_kwargs,
    _venv_python,
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
    def test_includes_the_env_when_it_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        env_dir = tmp_path / "cuda_env"
        env_dir.mkdir()
        assert _find_stale_cuda_dirs(env_dir) == [env_dir]

    def test_includes_the_legacy_target_dir(self, tmp_path, monkeypatch):
        # Installs made before the switch to a private venv used --target
        # cuda_packages; several gigabytes that nothing else would remove.
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        legacy = tmp_path / "cuda_packages"
        legacy.mkdir()
        assert _find_stale_cuda_dirs(tmp_path / "cuda_env") == [legacy]

    def test_empty_when_nothing_installed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        assert _find_stale_cuda_dirs(tmp_path / "cuda_env") == []

    def test_includes_other_snap_revisions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        current = tmp_path / "1682"
        old = tmp_path / "1662"
        for revision in (current, old):
            (revision / "cuda_env").mkdir(parents=True)
        monkeypatch.setenv("SNAP_USER_DATA", str(current))

        stale = _find_stale_cuda_dirs(current / "cuda_env")

        assert set(stale) == {current / "cuda_env", old / "cuda_env"}

    def test_skips_the_current_symlink(self, tmp_path, monkeypatch):
        # ~/snap/<name>/current symlinks to the active revision; following it
        # would list the same directory twice under two names.
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        revision = tmp_path / "1682"
        (revision / "cuda_env").mkdir(parents=True)
        (tmp_path / "current").symlink_to(revision)
        monkeypatch.setenv("SNAP_USER_DATA", str(revision))

        assert _find_stale_cuda_dirs(revision / "cuda_env") == [revision / "cuda_env"]


class TestCleanupOldCudaPackages:
    def test_removes_stale_directory(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        env_dir = tmp_path / "cuda_env"
        (env_dir / "torch").mkdir(parents=True)

        _cleanup_old_cuda_packages(env_dir)

        assert not env_dir.exists()

    def test_reports_progress(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        env_dir = tmp_path / "cuda_env"
        env_dir.mkdir()
        messages = []

        _cleanup_old_cuda_packages(env_dir, messages.append)

        assert any("Removing previous CUDA packages" in m for m in messages)

    def test_survives_removal_failure(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        env_dir = tmp_path / "cuda_env"
        env_dir.mkdir()

        with patch("shutil.rmtree", side_effect=OSError("permission denied")):
            _cleanup_old_cuda_packages(env_dir)  # must not raise

    def test_install_cleans_before_installing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.setenv("FLATPAK_ID", "io.github.chidiwilliams.buzz")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        stale_marker = tmp_path / "buzz" / "cuda_env" / "torch" / "stale.txt"
        stale_marker.parent.mkdir(parents=True)
        stale_marker.write_text("old install")

        with patch("buzz.cuda_manager._create_cuda_env", return_value=["pip", "install"]):
            with patch("buzz.cuda_manager._run_install") as run_install:
                install_cuda()

        assert not stale_marker.exists()
        assert run_install.called


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


class TestGetCudaEnvDir:
    def test_snap_uses_snap_user_data(self, monkeypatch, tmp_path):
        snap_dir = tmp_path / "snap_data"
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        monkeypatch.setenv("SNAP_USER_DATA", str(snap_dir))
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        assert get_cuda_env_dir() == snap_dir / "cuda_env"

    def test_snap_falls_back_to_home_when_no_snap_user_data(self, monkeypatch):
        monkeypatch.setenv("SNAP", "/snap/buzz/current")
        monkeypatch.setenv("SNAP_NAME", "buzz")
        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        assert get_cuda_env_dir() == Path.home() / ".local" / "share" / "buzz" / "cuda_env"

    def test_flatpak_uses_xdg_data_home(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.setenv("FLATPAK_ID", "io.github.chidiwilliams.buzz")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert get_cuda_env_dir() == tmp_path / "buzz" / "cuda_env"

    def test_falls_back_to_the_buzz_data_dir(self, monkeypatch):
        # Never a shared site-packages: an uninstall has to be able to take the
        # multi-gigabyte install with it.
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        from platformdirs import user_data_dir

        assert get_cuda_root_dir() == Path(user_data_dir("Buzz"))
        assert get_cuda_env_dir().name == "cuda_env"


class TestGetCudaEnvSitePackages:
    def test_finds_posix_layout(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        site_packages = tmp_path / "lib" / "python3.13" / "site-packages"
        site_packages.mkdir(parents=True)
        assert get_cuda_env_site_packages(tmp_path) == site_packages

    def test_finds_windows_layout(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        site_packages = tmp_path / "Lib" / "site-packages"
        site_packages.mkdir(parents=True)
        assert get_cuda_env_site_packages(tmp_path) == site_packages

    def test_returns_none_when_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert get_cuda_env_site_packages(tmp_path) is None


class TestVenvPython:
    def test_windows_layout(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "win32")
        assert _venv_python(tmp_path) == tmp_path / "Scripts" / "python.exe"

    def test_posix_layout(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        assert _venv_python(tmp_path) == tmp_path / "bin" / "python"


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


class TestGetBasePython:
    def test_returns_base_executable_when_not_frozen(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
        assert _get_base_python() == getattr(sys, "_base_executable", None) or sys.executable

    def test_prefers_the_bundled_interpreter_when_frozen(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(sys, "platform", "linux")
        bundled = tmp_path / "python" / "python3"
        bundled.parent.mkdir(parents=True)
        bundled.write_text("")

        assert _get_base_python() == str(bundled)

    def test_falls_back_to_path_when_frozen_without_bundle(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        with patch("shutil.which", return_value="/usr/bin/python3"):
            assert _get_base_python() == "/usr/bin/python3"

    def test_raises_when_frozen_and_no_interpreter(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="Could not find a Python interpreter"):
                _get_base_python()


class TestFindUv:
    def test_prefers_the_snap_bundled_uv(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SNAP", str(tmp_path))
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            assert _find_uv() == str(tmp_path / "bin" / "uv")

    def test_falls_back_to_path(self, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run", return_value=MagicMock(returncode=0)):
                assert _find_uv() == "/usr/bin/uv"

    def test_returns_none_when_uv_is_unusable(self, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        with patch("shutil.which", return_value="/usr/bin/uv"):
            with patch("subprocess.run", side_effect=OSError):
                assert _find_uv() is None


class TestCreateCudaEnv:
    def test_uses_uv_when_available(self, tmp_path):
        env_dir = tmp_path / "cuda_env"
        with patch("buzz.cuda_manager._find_uv", return_value="/usr/bin/uv"):
            with patch("buzz.cuda_manager._get_base_python", return_value="/usr/bin/python3"):
                with patch("buzz.cuda_manager._run_command") as run_command:
                    cmd = _create_cuda_env(env_dir)

        assert run_command.call_args[0][0][:2] == ["/usr/bin/uv", "venv"]
        assert cmd[:3] == ["/usr/bin/uv", "pip", "install"]

    def test_falls_back_to_the_venv_module(self, tmp_path):
        # The snap's Python has neither pip nor ensurepip, the Windows bundle
        # has both; only one of the two paths can work on a given platform.
        env_dir = tmp_path / "cuda_env"
        with patch("buzz.cuda_manager._find_uv", return_value=None):
            with patch("buzz.cuda_manager._get_base_python", return_value="/usr/bin/python3"):
                with patch("subprocess.run", return_value=MagicMock(returncode=0)) as run:
                    cmd = _create_cuda_env(env_dir)

        assert run.call_args[0][0] == ["/usr/bin/python3", "-m", "venv", str(env_dir)]
        assert cmd[1:] == ["-m", "pip", "install", "--no-cache-dir"]

    def test_raises_when_venv_creation_fails(self, tmp_path):
        env_dir = tmp_path / "cuda_env"
        failure = MagicMock(returncode=1, stderr="no ensurepip", stdout="")
        with patch("buzz.cuda_manager._find_uv", return_value=None):
            with patch("buzz.cuda_manager._get_base_python", return_value="/usr/bin/python3"):
                with patch("subprocess.run", return_value=failure):
                    with pytest.raises(RuntimeError, match="Could not create the environment"):
                        _create_cuda_env(env_dir)


class TestRunInstall:
    def test_calls_the_installer_with_packages(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["Collecting torch\n", "Successfully installed\n"])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            _run_install(
                [sys.executable, "-m", "pip", "install"],
                ["torch==2.0.0"],
                extra_args=["--index-url", "https://example.com"],
            )

        cmd = mock_popen.call_args[0][0]
        assert "torch==2.0.0" in cmd
        assert "--index-url" in cmd

    def test_raises_on_nonzero_exit(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.returncode = 1
        mock_proc.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="pip install failed"):
                _run_install([sys.executable, "-m", "pip", "install"], ["torch==2.0.0"])

    def test_calls_progress_callback(self):
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n"])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        calls = []
        with patch("subprocess.Popen", return_value=mock_proc):
            _run_install([sys.executable, "-m", "pip", "install"], ["pkg"], progress_callback=calls.append)

        assert "line1" in calls
        assert "line2" in calls


class TestInstallCuda:
    @pytest.fixture(autouse=True)
    def _isolated_env(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SNAP", raising=False)
        monkeypatch.delenv("SNAP_NAME", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        monkeypatch.setattr(
            "buzz.cuda_manager.get_cuda_root_dir", lambda: tmp_path
        )

    def test_installs_into_the_private_env(self):
        with patch("buzz.cuda_manager._create_cuda_env") as create_env:
            with patch("buzz.cuda_manager._run_install") as run_install:
                install_cuda()

        assert create_env.called
        assert run_install.call_count == 2
        # No --user, no --break-system-packages: nothing outside the private env.
        for call_args in run_install.call_args_list:
            assert "--user" not in (call_args.kwargs.get("extra_args") or [])

    def test_passes_progress_callback(self):
        messages = []
        with patch("buzz.cuda_manager._create_cuda_env"):
            with patch("buzz.cuda_manager._run_install"):
                install_cuda(progress_callback=messages.append)

        assert any("NVIDIA" in m for m in messages)
        assert any("PyTorch" in m for m in messages)

    def test_excludes_linux_only_packages_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        captured = []

        with patch("buzz.cuda_manager._create_cuda_env"):
            with patch(
                "buzz.cuda_manager._run_install",
                side_effect=lambda cmd, packages, **kwargs: captured.append(packages),
            ):
                install_cuda()

        nvidia_pkgs = captured[0]
        for pkg in CUDA_NVIDIA_PACKAGES_LINUX:
            assert pkg not in nvidia_pkgs
