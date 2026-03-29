import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGetCudaTargetDir:
    def test_returns_snap_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SNAP_USER_DATA", str(tmp_path))
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        from buzz.cuda_setup import _get_cuda_target_dir
        result = _get_cuda_target_dir()
        assert result == tmp_path / "cuda_packages"

    def test_returns_flatpak_path(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.setenv("FLATPAK_ID", "io.github.chidiwilliams.buzz")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        from buzz.cuda_setup import _get_cuda_target_dir
        result = _get_cuda_target_dir()
        assert result == tmp_path / "buzz" / "cuda_packages"

    def test_returns_none_when_no_env(self, monkeypatch):
        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)
        from buzz.cuda_setup import _get_cuda_target_dir
        result = _get_cuda_target_dir()
        assert result is None

    def test_flatpak_falls_back_to_home(self, monkeypatch):
        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.setenv("FLATPAK_ID", "io.github.chidiwilliams.buzz")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        from buzz.cuda_setup import _get_cuda_target_dir
        result = _get_cuda_target_dir()
        assert result is not None
        assert "cuda_packages" in str(result)


class TestGetSitePackagesDirs:
    def test_adds_cuda_target_to_sys_path(self, monkeypatch, tmp_path):
        cuda_target = tmp_path / "cuda_packages"
        cuda_target.mkdir()
        monkeypatch.setenv("SNAP_USER_DATA", str(tmp_path))
        monkeypatch.delenv("FLATPAK_ID", raising=False)

        from buzz.cuda_setup import _get_site_packages_dirs
        dirs = _get_site_packages_dirs()

        assert cuda_target in dirs
        assert str(cuda_target) in sys.path

    def test_returns_list_including_existing_site_packages(self, monkeypatch):
        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)

        from buzz.cuda_setup import _get_site_packages_dirs
        dirs = _get_site_packages_dirs()
        assert isinstance(dirs, list)


class TestCollectCudaLibDirs:
    def test_includes_torch_lib(self, tmp_path):
        torch_lib = tmp_path / "torch" / "lib"
        torch_lib.mkdir(parents=True)

        from buzz.cuda_setup import _collect_cuda_lib_dirs
        dirs = _collect_cuda_lib_dirs(tmp_path)
        assert str(torch_lib) in dirs

    def test_includes_nvidia_package_libs(self, tmp_path):
        nvidia_cublas = tmp_path / "nvidia" / "cublas" / "lib"
        nvidia_cublas.mkdir(parents=True)

        from buzz.cuda_setup import _collect_cuda_lib_dirs
        dirs = _collect_cuda_lib_dirs(tmp_path)
        assert str(nvidia_cublas) in dirs

    def test_returns_empty_when_no_dirs_exist(self, tmp_path):
        from buzz.cuda_setup import _collect_cuda_lib_dirs
        dirs = _collect_cuda_lib_dirs(tmp_path)
        assert dirs == []


class TestGetNvidiaPackageLibDirs:
    def test_finds_nvidia_lib_dirs(self, monkeypatch, tmp_path):
        sp = tmp_path / "site-packages"
        nvidia_lib = sp / "nvidia" / "cublas" / "lib"
        nvidia_lib.mkdir(parents=True)

        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)

        with patch("buzz.cuda_setup._get_site_packages_dirs", return_value=[sp]):
            from buzz.cuda_setup import _get_nvidia_package_lib_dirs
            dirs = _get_nvidia_package_lib_dirs()

        assert nvidia_lib in dirs

    def test_finds_torch_lib_dir(self, monkeypatch, tmp_path):
        sp = tmp_path / "site-packages"
        torch_lib = sp / "torch" / "lib"
        torch_lib.mkdir(parents=True)

        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)

        with patch("buzz.cuda_setup._get_site_packages_dirs", return_value=[sp]):
            from buzz.cuda_setup import _get_nvidia_package_lib_dirs
            dirs = _get_nvidia_package_lib_dirs()

        assert torch_lib in dirs


class TestSetupLinuxCuda:
    def test_skips_when_no_cuda_target(self, monkeypatch):
        monkeypatch.delenv("SNAP_USER_DATA", raising=False)
        monkeypatch.delenv("FLATPAK_ID", raising=False)

        with patch("buzz.cuda_setup._get_cuda_target_dir", return_value=None):
            from buzz.cuda_setup import _setup_linux_cuda
            _setup_linux_cuda()  # should not raise

    def test_skips_when_cuda_target_does_not_exist(self, monkeypatch, tmp_path):
        nonexistent = tmp_path / "nonexistent"
        with patch("buzz.cuda_setup._get_cuda_target_dir", return_value=nonexistent):
            from buzz.cuda_setup import _setup_linux_cuda
            _setup_linux_cuda()  # should not raise

    def test_skips_when_no_torch_lib(self, monkeypatch, tmp_path):
        cuda_target = tmp_path / "cuda_packages"
        cuda_target.mkdir()
        with patch("buzz.cuda_setup._get_cuda_target_dir", return_value=cuda_target):
            from buzz.cuda_setup import _setup_linux_cuda
            _setup_linux_cuda()  # should not raise

    def test_reexecs_when_sentinel_not_in_ld_path(self, monkeypatch, tmp_path):
        cuda_target = tmp_path / "cuda_packages"
        torch_lib = cuda_target / "torch" / "lib"
        torch_lib.mkdir(parents=True)

        monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)

        with patch("buzz.cuda_setup._get_cuda_target_dir", return_value=cuda_target):
            with patch("buzz.cuda_setup._collect_cuda_lib_dirs", return_value=[str(torch_lib)]):
                with patch("os.execv", side_effect=OSError("test")) as mock_execv:
                    with patch("buzz.cuda_setup._preload_linux_libraries_fallback") as mock_fallback:
                        from buzz.cuda_setup import _setup_linux_cuda
                        _setup_linux_cuda()

                mock_fallback.assert_called_once()

    def test_no_reexec_when_sentinel_already_in_ld_path(self, monkeypatch, tmp_path):
        cuda_target = tmp_path / "cuda_packages"
        torch_lib = cuda_target / "torch" / "lib"
        torch_lib.mkdir(parents=True)

        monkeypatch.setenv("LD_LIBRARY_PATH", str(torch_lib))

        with patch("buzz.cuda_setup._get_cuda_target_dir", return_value=cuda_target):
            with patch("os.execv") as mock_execv:
                from buzz.cuda_setup import _setup_linux_cuda
                _setup_linux_cuda()

            mock_execv.assert_not_called()


class TestSetupWindowsDllDirectories:
    def test_calls_add_dll_directory(self, tmp_path):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()

        with patch("buzz.cuda_setup._get_nvidia_package_lib_dirs", return_value=[lib_dir]):
            with patch("buzz.cuda_setup.os") as mock_os:
                from buzz.cuda_setup import _setup_windows_dll_directories
                _setup_windows_dll_directories()

            mock_os.add_dll_directory.assert_called_once_with(str(lib_dir))

    def test_logs_warning_when_no_lib_dirs(self):
        with patch("buzz.cuda_setup._get_nvidia_package_lib_dirs", return_value=[]):
            with patch("buzz.cuda_setup.logger") as mock_logger:
                from buzz.cuda_setup import _setup_windows_dll_directories
                _setup_windows_dll_directories()

            mock_logger.warning.assert_called_once()


class TestSetupCudaLibraries:
    def test_calls_windows_setup_on_windows(self):
        with patch("platform.system", return_value="Windows"):
            with patch("buzz.cuda_setup._setup_windows_dll_directories") as mock_win:
                from buzz.cuda_setup import setup_cuda_libraries
                setup_cuda_libraries()
            mock_win.assert_called_once()

    def test_calls_linux_setup_on_linux(self):
        with patch("platform.system", return_value="Linux"):
            with patch("buzz.cuda_setup._setup_linux_cuda") as mock_linux:
                from buzz.cuda_setup import setup_cuda_libraries
                setup_cuda_libraries()
            mock_linux.assert_called_once()

    def test_does_nothing_on_macos(self):
        with patch("platform.system", return_value="Darwin"):
            with patch("buzz.cuda_setup._setup_windows_dll_directories") as mock_win:
                with patch("buzz.cuda_setup._setup_linux_cuda") as mock_linux:
                    from buzz.cuda_setup import setup_cuda_libraries
                    setup_cuda_libraries()
            mock_win.assert_not_called()
            mock_linux.assert_not_called()


class TestPreloadLinuxLibrariesFallback:
    def test_loads_so_files(self, tmp_path):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        so_file = lib_dir / "libfoo.so.1"
        so_file.touch()

        with patch("buzz.cuda_setup._get_nvidia_package_lib_dirs", return_value=[lib_dir]):
            with patch("ctypes.CDLL") as mock_cdll:
                from buzz.cuda_setup import _preload_linux_libraries_fallback
                _preload_linux_libraries_fallback()
            mock_cdll.assert_called()

    def test_skips_libnvblas(self, tmp_path):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        skip_file = lib_dir / "libnvblas.so.1"
        skip_file.touch()

        with patch("buzz.cuda_setup._get_nvidia_package_lib_dirs", return_value=[lib_dir]):
            with patch("ctypes.CDLL") as mock_cdll:
                from buzz.cuda_setup import _preload_linux_libraries_fallback
                _preload_linux_libraries_fallback()
            mock_cdll.assert_not_called()
