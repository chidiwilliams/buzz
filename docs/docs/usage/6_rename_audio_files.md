---
title: Rename Audio Files
---

Bulk-rename a folder of audio files based on the first few transcribed words
of each file. Useful for projects where every audio clip should be named after
what's actually said in it — voiceover sets, interview clips, dubbing assets,
sermon archives, lecture recordings, etc.

This feature is **fully offline** and reuses Buzz's existing Whisper backends
(Whisper, Whisper.cpp, Faster-Whisper, HuggingFace). No third-party API key
or internet connection is required.

## Workflow

1. **File → Rename Audio Files…** to open the dialog.
2. **Browse…** for a folder of audio files (`.mp3 .wav .m4a .flac .ogg .aac
   .opus`).
3. Pick a model type and language. For most use cases, `whispercpp` + `small`
   gives the best balance of speed and accuracy.
4. Adjust the optional knobs:
   - **Trim seconds** — how much of each clip to send to Whisper. Default 5s
     is enough for most voiceovers.
   - **Words** — how many leading words to use in the new filename.
     Default 6.
   - **Max length** — truncate filenames at this many characters at a word
     boundary. Default 50.
   - **Keep numeric prefix** — if the original filenames start with `01_`,
     `02_`, `03_`…, preserve that prefix on the new names. Useful for
     ordered audio sets where position matters.
5. Click **Preview Renames**. Each file is transcribed in turn; proposed
   names appear in the table as they're ready.
6. Inspect the table. Each row is colour-coded:
   - 🟢 ready to rename
   - ⚪ already correctly named (no change)
   - 🔵 already applied
   - 🔴 error (e.g. silent clip, corrupt file)
7. Override any proposed name by **double-clicking** the *Proposed* cell and
   typing a new name. Right-click any row for **Skip**, **Reset to AI
   suggestion**, etc.
8. Click **Apply Renames**.
9. An `.undo_YYYYMMDD_HHMMSS.json` file is written into the audio folder.

## Undoing a batch

Click **Undo Last Batch** in the dialog (or run
`buzz rename --undo /path/to/.undo_*.json` on the command line). Buzz will
walk the log and reverse every rename that was applied.

If you've manually edited or moved any of the files between the apply and the
undo, those entries will fail individually — the rest will still be reverted
correctly.

## Tips

- The default 5-second trim is enough for typical voiceover clips. Bump it up
  to 10–15 seconds for clips where the first sentence is genuinely long, or
  for languages where Whisper does better with more context.
- Whisper.cpp on the `tiny` model is the fastest option but the least
  accurate. `small` or `medium` give noticeably better filenames if you have
  the CPU/GPU budget.
- Collisions are resolved automatically: if two clips would end up with the
  same name, the second gets `_1`, `_2`, etc. appended. Existing files in the
  folder that aren't part of the batch are also avoided.
- The whole pipeline is offline. Buzz never sends audio anywhere.

## Command-line equivalent

The same feature is available from the CLI as `buzz rename`. See the
[CLI documentation](../cli.md#rename) for the full option list.
