---
title: Plugins
---

Plugins are available since Buzz version **1.4.5**.

Plugins extend Buzz's transcription pipeline without requiring changes to the core application. They can process audio before transcription, modify transcription results, and run custom actions after a transcription is saved (such as exporting to additional formats or generating summaries).

**To manage plugins:**

- Open **Help → Plugins**.
- Enable or disable individual plugins using the toggle next to each one.
- Drag plugins to change the order they run in.
- Click the settings icon next to a plugin to configure its options.
- Add a community plugin by clicking **Add by URL** and pasting a link to a `.zip` file.

## Built-in plugins

### AI Summary

Generates a summary of the transcript using an OpenAI-compatible API (e.g. OpenAI, Ollama) and saves it to the transcript's Notes field and/or a text file next to the source audio. Requires an API key and base URL.

### Enhanced Language Detection

Automatically detects the spoken language before transcription begins using a local Whisper model. Useful when transcribing files with unknown languages. Can optionally download the tiny Whisper model if no local model is available.

### Export to DOCX

Exports the completed transcript to a Microsoft Word `.docx` file. Timestamps can optionally be included. No extra dependencies required.

### Resize Transcript

Automatically regroups word-level transcript segments into subtitle-sized chunks after transcription. Supports merging by silence gaps, splitting on punctuation, and enforcing a maximum subtitle length. Requires word-level timings to be enabled on the transcription.

### Skip Already Transcribed

Skips transcription if results for the imported file have already been produced. Supports two detection methods (both can be enabled at the same time):

- **Check for existing result files** *(enabled by default)* — looks for a `.txt`, `.srt`, or `.vtt` file matching the audio filename in the same folder. If found, the existing transcript is imported and the file is marked as **Skipped** without re-running the model.
- **Check in transcription database** — checks whether this filename already has a completed transcription in Buzz's database. If found, the prior transcript segments are copied to the new entry and the file is marked as **Skipped**.

This is useful when re-importing a folder of files where some have already been transcribed, or when watching a folder automatically.

## Building your own plugin

The built-in plugins are a good starting point for writing a custom plugin. Browse the source code in [buzz/plugins](https://github.com/chidiwilliams/buzz/tree/main/buzz/plugins) to see how they are structured and which hooks they use. 

If you build something useful, please share it with the Buzz community! Open a [GitHub Discussion](https://github.com/chidiwilliams/buzz/discussions) or submit a pull request to have your plugin considered for inclusion as a built-in.
