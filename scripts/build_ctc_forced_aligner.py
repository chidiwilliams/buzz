"""Patch and build the ctc_forced_aligner C++ extension in-place.

Used both by the wheel build (``hatch_build.py``) and by ``make test``, so a
plain source checkout can import ``ctc_forced_aligner`` without building a wheel
first.

By default this is a no-op when the compiled extension is already present and
newer than its source. Pass ``--force`` to rebuild regardless.
"""
import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALIGNER_DIR = PROJECT_ROOT / "ctc_forced_aligner"
ALIGNER_PKG = ALIGNER_DIR / "ctc_forced_aligner"
SOURCE_FILE = ALIGNER_PKG / "forced_align_impl.cpp"
PATCHES_DIR = PROJECT_ROOT / "patches"


def _compiled_extensions():
    return [p for pattern in ("*.pyd", "*.so") for p in ALIGNER_PKG.glob(pattern)]


def is_up_to_date():
    """True when a compiled extension exists and is newer than the C++ source."""
    extensions = _compiled_extensions()
    if not extensions:
        return False
    if not SOURCE_FILE.exists():
        return True
    newest = max(p.stat().st_mtime for p in extensions)
    return newest >= SOURCE_FILE.stat().st_mtime


def apply_patches():
    """Apply patches/ctc_forced_aligner_*.patch, skipping already applied ones.

    Uses --check first to avoid touching the working tree unnecessarily,
    which is safer in a detached-HEAD submodule.
    """
    for patch_file in sorted(PATCHES_DIR.glob("ctc_forced_aligner_*.patch")):
        # Dry-run forward: succeeds only if patch is NOT yet applied.
        check_forward = subprocess.run(
            ["git", "apply", "--check", "--ignore-whitespace", str(patch_file)],
            cwd=ALIGNER_DIR,
            capture_output=True,
            text=True,
        )
        if check_forward.returncode == 0:
            # Patch can be applied — do it for real.
            subprocess.run(
                ["git", "apply", "--ignore-whitespace", str(patch_file)],
                cwd=ALIGNER_DIR,
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"Applied patch: {patch_file.name}")
        else:
            # Dry-run failed — either already applied or genuinely broken.
            check_reverse = subprocess.run(
                ["git", "apply", "--check", "--reverse", "--ignore-whitespace", str(patch_file)],
                cwd=ALIGNER_DIR,
                capture_output=True,
                text=True,
            )
            if check_reverse.returncode == 0:
                print(f"Patch already applied (skipping): {patch_file.name}")
            else:
                print(
                    f"WARNING: could not apply patch {patch_file.name}: {check_forward.stderr}",
                    file=sys.stderr,
                )


def build():
    """Patch the sources and compile the extension in-place."""
    if not ALIGNER_DIR.exists():
        raise FileNotFoundError(
            f"{ALIGNER_DIR} does not exist. Run 'git submodule update --init' first."
        )

    apply_patches()

    print("Building ctc_forced_aligner C++ extension...")
    result = subprocess.run(
        [sys.executable, "setup.py", "build_ext", "--inplace"],
        cwd=ALIGNER_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    print("Successfully built ctc_forced_aligner C++ extension")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even when the compiled extension is already up to date.",
    )
    args = parser.parse_args()

    if not args.force and is_up_to_date():
        print("ctc_forced_aligner C++ extension is up to date, skipping build")
        return

    try:
        build()
    except subprocess.CalledProcessError as e:
        print(f"Error building ctc_forced_aligner: {e}", file=sys.stderr)
        print(f"stdout: {e.stdout}", file=sys.stderr)
        print(f"stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
