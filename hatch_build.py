"""Custom build hook for hatchling to build whisper.cpp binaries."""
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
        except subprocess.CalledProcessError as e:
            print(f"Error building whisper.cpp: {e}", file=sys.stderr)
            print(f"stdout: {e.stdout}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print("Error: 'make' command not found. Please ensure make is installed.", file=sys.stderr)
            sys.exit(1)
