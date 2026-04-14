"""Download Buzz models for offline / air-gapped deployment.

Set BUZZ_MODEL_ROOT to control where models are stored:

    BUZZ_MODEL_ROOT=/mnt/nfs/buzz-models uv run python scripts/download-models.py

Without filters, downloads all standard sizes for all backends.
Use --model-type and --model-size to download selectively:

    uv run python scripts/download-models.py --model-type fasterwhisper --model-size small
    uv run python scripts/download-models.py --model-type whispercpp --model-size tiny base small
"""

import argparse
import os
import sys

# Mirror the HF_HOME logic from buzz/buzz.py so downloads go to the right place
_model_root = os.environ.get("BUZZ_MODEL_ROOT")
if _model_root:
    os.environ.setdefault("HF_HOME", os.path.dirname(_model_root))

from PyQt6.QtCore import QCoreApplication

from buzz.model_loader import (
    ModelType,
    WhisperModelSize,
    TranscriptionModel,
    ModelDownloader,
    model_root_dir,
)

# CLI name -> ModelType mapping (matches buzz/cli.py convention)
MODEL_TYPE_MAP = {
    "whisper": ModelType.WHISPER,
    "whispercpp": ModelType.WHISPER_CPP,
    "fasterwhisper": ModelType.FASTER_WHISPER,
}

# Standard sizes to download (excludes CUSTOM and LUMII)
STANDARD_SIZES = [s for s in WhisperModelSize if s not in (WhisperModelSize.CUSTOM, WhisperModelSize.LUMII)]


def download(model_types, model_sizes):
    total = len(model_types) * len(model_sizes)
    done = 0
    failed = []

    for mt in model_types:
        for size in model_sizes:
            done += 1
            label = f"[{done}/{total}] {mt.value} / {size.value}"

            model = TranscriptionModel(model_type=mt, whisper_model_size=size)
            if model.get_local_model_path() is not None:
                print(f"{label} — already present, skipping")
                continue

            print(f"{label} — downloading...")
            downloader = ModelDownloader(model=model)
            downloader.signals.error.connect(lambda e, lbl=label: failed.append((lbl, e)))
            downloader.run()

            if model.get_local_model_path() is not None:
                print(f"{label} — done")
            else:
                print(f"{label} — FAILED", file=sys.stderr)
                failed.append((label, "model path not found after download"))

    return failed


def main():
    parser = argparse.ArgumentParser(description="Download Buzz models for offline use")
    parser.add_argument(
        "--model-type",
        choices=list(MODEL_TYPE_MAP.keys()),
        nargs="+",
        help="Model backends to download (default: all)",
    )
    parser.add_argument(
        "--model-size",
        choices=[s.value for s in STANDARD_SIZES],
        nargs="+",
        help="Model sizes to download (default: all standard sizes)",
    )
    args = parser.parse_args()

    model_types = (
        [MODEL_TYPE_MAP[t] for t in args.model_type]
        if args.model_type
        else list(MODEL_TYPE_MAP.values())
    )
    model_sizes = (
        [WhisperModelSize(s) for s in args.model_size]
        if args.model_size
        else STANDARD_SIZES
    )

    print(f"Model root: {model_root_dir}")
    print(f"Backends:   {', '.join(t.value for t in model_types)}")
    print(f"Sizes:      {', '.join(s.value for s in model_sizes)}")
    print()

    failed = download(model_types, model_sizes)

    if failed:
        print(f"\n{len(failed)} download(s) failed:", file=sys.stderr)
        for label, err in failed:
            print(f"  {label}: {err}", file=sys.stderr)
        sys.exit(1)

    print("\nAll downloads complete.")


if __name__ == "__main__":
    # Minimal Qt app needed for PyQt signal machinery in ModelDownloader
    app = QCoreApplication(sys.argv)
    main()
