---
title: Preferences
sidebar_position: 4
---

Open the Preferences window from the Menu bar, or click `Ctrl/Cmd + ,`.

## General Preferences

### Default export file name

Sets the default export file name for file transcriptions. For
example, a value of `{{ input_file_name }} ({{ task }}d on {{ date_time }})` will save TXT exports
as `Input Filename (transcribed on 19-Sep-2023 20-39-25).txt` by default.

Available variables:

| Key               | Description                               | Example                                                          |
|-------------------|-------------------------------------------|------------------------------------------------------------------|
| `input_file_name` | File name of the imported file            | `audio` (e.g. if the imported file path was `/path/to/audio.wav` |
| `task`            | Transcription task                        | `transcribe`, `translate`                                        |
| `language`        | Language code                             | `en`, `fr`, `yo`, etc.                                           |
| `model_type`      | Model type                                | `Whisper`, `Whisper.cpp`, `Faster Whisper`, etc.                 |
| `model_size`      | Model size                                | `tiny`, `base`, `small`, `medium`, `large`, etc.                 |
| `date_time`       | Export time (format: `%d-%b-%Y %H-%M-%S`) | `19-Sep-2023 20-39-25`                                           |
