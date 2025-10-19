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

        except subprocess.CalledProcessError as e:
            print(f"Error building whisper.cpp: {e}", file=sys.stderr)
            print(f"stdout: {e.stdout}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print("Error: 'make' command not found. Please ensure make is installed.", file=sys.stderr)
            sys.exit(1)
