import subprocess
from unittest.mock import MagicMock, patch

import pytest

from buzz import pip_utils


class TestEnvironmentDetection:
    def test_is_snap(self, monkeypatch):
        monkeypatch.setenv("SNAP", "/snap/buzz")
        assert pip_utils.is_snap() is True

    def test_is_not_snap(self, monkeypatch):
        monkeypatch.delenv("SNAP", raising=False)
        assert pip_utils.is_snap() is False

    def test_is_flatpak(self, monkeypatch):
        monkeypatch.setenv("FLATPAK_ID", "org.buzz.Buzz")
        assert pip_utils.is_flatpak() is True

    def test_is_not_flatpak(self, monkeypatch):
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        assert pip_utils.is_flatpak() is False

    def test_in_virtualenv_when_prefixes_differ(self, monkeypatch):
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        monkeypatch.setattr(pip_utils.sys, "prefix", "/venv")
        monkeypatch.setattr(pip_utils.sys, "base_prefix", "/usr")
        assert pip_utils._in_virtualenv() is True

    def test_in_virtualenv_via_env_var(self, monkeypatch):
        monkeypatch.setattr(pip_utils.sys, "prefix", "/usr")
        monkeypatch.setattr(pip_utils.sys, "base_prefix", "/usr")
        monkeypatch.setenv("VIRTUAL_ENV", "/venv")
        assert pip_utils._in_virtualenv() is True

    def test_not_in_virtualenv(self, monkeypatch):
        monkeypatch.setattr(pip_utils.sys, "prefix", "/usr")
        monkeypatch.setattr(pip_utils.sys, "base_prefix", "/usr")
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        assert pip_utils._in_virtualenv() is False


class TestSubprocessHideWindowKwargs:
    def test_empty_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(pip_utils.sys, "platform", "linux")
        assert pip_utils.subprocess_hide_window_kwargs() == {}

    def test_windows_returns_startupinfo(self, monkeypatch):
        monkeypatch.setattr(pip_utils.sys, "platform", "win32")
        fake_si = MagicMock()
        monkeypatch.setattr(
            pip_utils.subprocess, "STARTUPINFO", lambda: fake_si, raising=False
        )
        monkeypatch.setattr(
            pip_utils.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False
        )
        monkeypatch.setattr(pip_utils.subprocess, "SW_HIDE", 0, raising=False)
        monkeypatch.setattr(
            pip_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
        )

        kwargs = pip_utils.subprocess_hide_window_kwargs()

        assert kwargs["startupinfo"] is fake_si
        assert kwargs["creationflags"] == 0x08000000


class TestGetPipCmd:
    def test_frozen_with_bundled_python(self, monkeypatch, tmp_path):
        bundled = tmp_path / "python"
        bundled.mkdir()
        python_bin = bundled / "python3"
        python_bin.write_text("")

        monkeypatch.setattr(pip_utils.sys, "frozen", True, raising=False)
        monkeypatch.setattr(pip_utils.sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(pip_utils.sys, "platform", "linux")

        assert pip_utils.get_pip_cmd() == [str(python_bin), "-m", "pip"]

    def test_frozen_falls_back_to_path_interpreter(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pip_utils.sys, "frozen", True, raising=False)
        monkeypatch.setattr(pip_utils.sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(pip_utils.sys, "platform", "linux")

        with patch("shutil.which", side_effect=lambda c: "/usr/bin/python3" if c == "python3" else None):
            assert pip_utils.get_pip_cmd() == ["/usr/bin/python3", "-m", "pip"]

    def test_frozen_no_interpreter_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pip_utils.sys, "frozen", True, raising=False)
        monkeypatch.setattr(pip_utils.sys, "_MEIPASS", str(tmp_path), raising=False)
        monkeypatch.setattr(pip_utils.sys, "platform", "linux")

        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError):
                pip_utils.get_pip_cmd()

    def test_non_frozen_pip_available(self, monkeypatch):
        monkeypatch.setattr(pip_utils.sys, "frozen", False, raising=False)
        monkeypatch.setattr(pip_utils.sys, "executable", "/usr/bin/python3")

        probe = MagicMock(returncode=0)
        with patch.object(pip_utils.subprocess, "run", return_value=probe) as run:
            assert pip_utils.get_pip_cmd() == ["/usr/bin/python3", "-m", "pip"]
            run.assert_called_once()

    def test_non_frozen_bootstraps_pip(self, monkeypatch):
        monkeypatch.setattr(pip_utils.sys, "frozen", False, raising=False)
        monkeypatch.setattr(pip_utils.sys, "executable", "/usr/bin/python3")

        probe = MagicMock(returncode=1)
        bootstrap = MagicMock(returncode=0)
        with patch.object(pip_utils.subprocess, "run", side_effect=[probe, bootstrap]):
            assert pip_utils.get_pip_cmd() == ["/usr/bin/python3", "-m", "pip"]

    def test_non_frozen_probe_raises_then_bootstrap_succeeds(self, monkeypatch):
        monkeypatch.setattr(pip_utils.sys, "frozen", False, raising=False)
        monkeypatch.setattr(pip_utils.sys, "executable", "/usr/bin/python3")

        bootstrap = MagicMock(returncode=0)
        with patch.object(
            pip_utils.subprocess,
            "run",
            side_effect=[OSError("boom"), bootstrap],
        ):
            assert pip_utils.get_pip_cmd() == ["/usr/bin/python3", "-m", "pip"]

    def test_non_frozen_ensurepip_fails_raises(self, monkeypatch):
        monkeypatch.setattr(pip_utils.sys, "frozen", False, raising=False)
        monkeypatch.setattr(pip_utils.sys, "executable", "/usr/bin/python3")

        probe = MagicMock(returncode=1)
        bootstrap = MagicMock(returncode=1)
        with patch.object(pip_utils.subprocess, "run", side_effect=[probe, bootstrap]):
            with pytest.raises(RuntimeError):
                pip_utils.get_pip_cmd()


class TestPipInstall:
    def test_empty_packages_returns_early(self):
        with patch.object(pip_utils, "get_pip_cmd") as get_cmd:
            pip_utils.pip_install([])
            get_cmd.assert_not_called()

    def test_streams_output_to_callback(self, monkeypatch):
        monkeypatch.setattr(
            pip_utils, "get_pip_cmd", lambda: ["python", "-m", "pip"]
        )
        process = MagicMock()
        process.stdout = iter(["Collecting foo", "", "Installed foo"])
        process.returncode = 0

        received = []
        with patch.object(pip_utils.subprocess, "Popen", return_value=process):
            pip_utils.pip_install(["foo"], progress_callback=received.append)

        assert received == ["Collecting foo", "Installed foo"]
        process.wait.assert_called_once()

    def test_appends_extra_args(self, monkeypatch):
        monkeypatch.setattr(
            pip_utils, "get_pip_cmd", lambda: ["python", "-m", "pip"]
        )
        process = MagicMock()
        process.stdout = iter([])
        process.returncode = 0

        with patch.object(pip_utils.subprocess, "Popen", return_value=process) as popen:
            pip_utils.pip_install(["foo"], extra_args=["--no-deps"])

        cmd = popen.call_args[0][0]
        assert cmd[-1] == "--no-deps"
        assert "foo" in cmd

    def test_non_zero_returncode_raises(self, monkeypatch):
        monkeypatch.setattr(
            pip_utils, "get_pip_cmd", lambda: ["python", "-m", "pip"]
        )
        process = MagicMock()
        process.stdout = iter([])
        process.returncode = 1

        with patch.object(pip_utils.subprocess, "Popen", return_value=process):
            with pytest.raises(RuntimeError):
                pip_utils.pip_install(["foo"])
