"""Custom build hook for hatchling to build whisper.cpp binaries."""
import glob
import platform
import re
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def required_glibc_minor(paths) -> int:
    """The highest glibc 2.x symbol version any of the ELF files in `paths` needs.

    Binaries need the glibc of the machine they were compiled on, not the one
    we would like to support, so this is what the wheel tag has to promise.
    """
    highest = 0
    for path in paths:
        with open(path, "rb") as f:
            if f.read(4) != b"\x7fELF":
                continue
            data = f.read()
        for match in re.finditer(rb"GLIBC_2\.(\d+)", data):
            highest = max(highest, int(match.group(1)))
    return highest


def platform_tag(included_files) -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        if machine not in ("x86_64", "amd64"):
            raise ValueError(f"Unsupported Linux architecture: {machine}. Only x86_64 is supported.")
        glibc_minor = required_glibc_minor(included_files)
        if glibc_minor == 0:
            # No binaries to inspect: fall back to the glibc we are building with.
            glibc_minor = int(platform.libc_ver()[1].split(".")[1])
        return f"py3-none-manylinux_2_{max(glibc_minor, 17)}_x86_64"
    if system == "darwin":
        if machine in ("x86_64", "amd64"):
            return "py3-none-macosx_10_9_x86_64"
        if machine in ("arm64", "aarch64"):
            return "py3-none-macosx_11_0_arm64"
        raise ValueError(f"Unsupported macOS architecture: {machine}")
    if system == "windows":
        if machine in ("x86_64", "amd64"):
            return "py3-none-win_amd64"
        raise ValueError(f"Unsupported Windows architecture: {machine}. Only x86_64 is supported.")
    raise ValueError(f"Unsupported operating system: {system}")


class CustomBuildHook(BuildHookInterface):
    """Build hook to compile whisper.cpp before building the package."""

    def initialize(self, version, build_data):
        """Run make buzz/whisper_cpp before building."""
        print("Running 'make buzz/whisper_cpp' to build whisper.cpp binaries...")

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

            # Patch and build the ctc_forced_aligner C++ extension in-place.
            # Shared with `make test` via scripts/build_ctc_forced_aligner.py;
            # --force so a wheel never ships a stale extension.
            result = subprocess.run(
                [sys.executable, str(project_root / "scripts" / "build_ctc_forced_aligner.py"), "--force"],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

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

            # Mark wheel as platform-specific since we're including compiled binaries,
            # tagged py3-none since the binaries do not depend on the Python version.
            if version == "standard":  # Only for wheel builds
                build_data["pure_python"] = False
                included = [project_root / p for p in build_data.get("force_include", {})]
                build_data["tag"] = platform_tag(included)
                print(f"Building wheel with tag: {build_data['tag']}")

        except subprocess.CalledProcessError as e:
            print(f"Error building whisper.cpp: {e}", file=sys.stderr)
            print(f"stdout: {e.stdout}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print("Error: 'make' command not found. Please ensure make is installed.", file=sys.stderr)
            sys.exit(1)
