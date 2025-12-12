"""Custom build hook for hatchling to build whisper.cpp binaries."""
import glob
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Build hook to compile whisper.cpp before building the package."""

    def initialize(self, version, build_data):
        """Run make buzz/whisper_cpp before building."""
        print("Running 'make buzz/whisper_cpp' to build whisper.cpp binaries...")

        # Mark wheel as platform-specific since we're including compiled binaries
        # But set tag to py3-none since binaries are standalone (no Python C extensions)
        if version == "standard":  # Only for wheel builds
            import platform

            build_data["pure_python"] = False

            # Determine the platform tag based on current OS and architecture
            system = platform.system().lower()
            machine = platform.machine().lower()

            if system == "linux":
                if machine in ("x86_64", "amd64"):
                    tag = "py3-none-manylinux_2_34_x86_64"
                else:
                    raise ValueError(f"Unsupported Linux architecture: {machine}. Only x86_64 is supported.")
            elif system == "darwin":
                if machine in ("x86_64", "amd64"):
                    tag = "py3-none-macosx_10_9_x86_64"
                elif machine in ("arm64", "aarch64"):
                    tag = "py3-none-macosx_11_0_arm64"
                else:
                    raise ValueError(f"Unsupported macOS architecture: {machine}")
            elif system == "windows":
                if machine in ("x86_64", "amd64"):
                    tag = "py3-none-win_amd64"
                else:
                    raise ValueError(f"Unsupported Windows architecture: {machine}. Only x86_64 is supported.")
            else:
                raise ValueError(f"Unsupported operating system: {system}")

            if tag:
                build_data["tag"] = tag
                print(f"Building wheel with tag: {tag}")

        # Get the project root directory
        project_root = Path(self.root)

        try:
            # Run the make command
            result = subprocess.run(
                ["make", "buzz/whisper_cpp"],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            print("Successfully built whisper.cpp binaries")

            # Run the make command for translation files
            result = subprocess.run(
                ["make", "translation_mo"],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            print("Successfully compiled translation files")

            # Build ctc_forced_aligner C++ extension in-place
            print("Building ctc_forced_aligner C++ extension...")
            ctc_aligner_dir = project_root / "ctc_forced_aligner"
            result = subprocess.run(
                [sys.executable, "setup.py", "build_ext", "--inplace"],
                cwd=ctc_aligner_dir,
                check=True,
                capture_output=True,
                text=True
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            print("Successfully built ctc_forced_aligner C++ extension")

            # Force include all files in buzz/whisper_cpp directory
            whisper_cpp_dir = project_root / "buzz" / "whisper_cpp"
            if whisper_cpp_dir.exists():
                # Get all files in the whisper_cpp directory
                whisper_files = glob.glob(str(whisper_cpp_dir / "**" / "*"), recursive=True)

                # Filter only files (not directories)
                whisper_files = [f for f in whisper_files if Path(f).is_file()]

                # Add them to force_include
                if 'force_include' not in build_data:
                    build_data['force_include'] = {}

                for file_path in whisper_files:
                    # Convert to relative path from project root
                    rel_path = Path(file_path).relative_to(project_root)
                    build_data['force_include'][str(rel_path)] = str(rel_path)

                print(f"Force including {len(whisper_files)} files from buzz/whisper_cpp/")
            else:
                print(f"Warning: {whisper_cpp_dir} does not exist after build", file=sys.stderr)

            # Force include all files in demucs directory
            demucs_dir = project_root / "demucs_repo"
            if demucs_dir.exists():
                # Get all files in the demucs directory
                demucs_files = glob.glob(str(demucs_dir / "**" / "*"), recursive=True)

                # Filter only files (not directories)
                demucs_files = [f for f in demucs_files if Path(f).is_file()]

                # Add them to force_include
                if 'force_include' not in build_data:
                    build_data['force_include'] = {}

                for file_path in demucs_files:
                    # Convert to relative path from project root
                    rel_path = Path(file_path).relative_to(project_root)
                    build_data['force_include'][str(rel_path)] = str(rel_path)

                print(f"Force including {len(demucs_files)} files from demucs_repo/")
            else:
                print(f"Warning: {demucs_dir} does not exist", file=sys.stderr)

            # Force include all .mo files from buzz/locale directory
            locale_dir = project_root / "buzz" / "locale"
            if locale_dir.exists():
                # Get all .mo files in the locale directory
                locale_files = glob.glob(str(locale_dir / "**" / "*.mo"), recursive=True)

                # Add them to force_include
                if 'force_include' not in build_data:
                    build_data['force_include'] = {}

                for file_path in locale_files:
                    # Convert to relative path from project root
                    rel_path = Path(file_path).relative_to(project_root)
                    build_data['force_include'][str(rel_path)] = str(rel_path)

                print(f"Force including {len(locale_files)} .mo files from buzz/locale/")
            else:
                print(f"Warning: {locale_dir} does not exist", file=sys.stderr)

            # Force include compiled extensions from ctc_forced_aligner
            ctc_aligner_pkg = project_root / "ctc_forced_aligner" / "ctc_forced_aligner"
            if ctc_aligner_pkg.exists():
                # Get all compiled extension files (.so, .pyd, .dll)
                extension_patterns = ["*.so", "*.pyd", "*.dll"]
                extension_files = []
                for pattern in extension_patterns:
                    extension_files.extend(glob.glob(str(ctc_aligner_pkg / pattern)))

                # Add them to force_include
                if 'force_include' not in build_data:
                    build_data['force_include'] = {}

                for file_path in extension_files:
                    # Convert to relative path from project root
                    rel_path = Path(file_path).relative_to(project_root)
                    build_data['force_include'][str(rel_path)] = str(rel_path)

                print(f"Force including {len(extension_files)} compiled extension(s) from ctc_forced_aligner/")
            else:
                print(f"Warning: {ctc_aligner_pkg} does not exist", file=sys.stderr)

        except subprocess.CalledProcessError as e:
            print(f"Error building whisper.cpp: {e}", file=sys.stderr)
            print(f"stdout: {e.stdout}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print("Error: 'make' command not found. Please ensure make is installed.", file=sys.stderr)
            sys.exit(1)
