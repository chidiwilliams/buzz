---
title: Preferences
sidebar_position: 4
---

Open the Preferences window from the Menu bar, or click `Ctrl/Cmd + ,`.

## General Preferences

### OpenAI API preferences

**API Key** - key to authenticate your requests to OpenAI API. To get API key from OpenAI see [this article](https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key).

**Base URL** - By default all requests are sent to API provided by OpenAI company. Their API URL is `https://api.openai.com/v1/`. Compatible APIs are also provided by other companies. List of available API URLs you can find on [discussion page](https://github.com/chidiwilliams/buzz/discussions/827)

### Default export file name

Sets the default export file name for file transcriptions. For
example, a value of `{{ input_file_name }} ({{ task }}d on {{ date_time }})` will save TXT exports
as `Input Filename (transcribed on 19-Sep-2023 20-39-25).txt` by default.

Available variables:

| Key               | Description                               | Example                                                          |
| ----------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| `input_file_name` | File name of the imported file            | `audio` (e.g. if the imported file path was `/path/to/audio.wav` |
| `task`            | Transcription task                        | `transcribe`, `translate`                                        |
| `language`        | Language code                             | `en`, `fr`, `yo`, etc.                                           |
| `model_type`      | Model type                                | `Whisper`, `Whisper.cpp`, `Faster Whisper`, etc.                 |
| `model_size`      | Model size                                | `tiny`, `base`, `small`, `medium`, `large`, etc.                 |
| `date_time`       | Export time (format: `%d-%b-%Y %H-%M-%S`) | `19-Sep-2023 20-39-25`                                           |

### Live transcript exports

Live transcription export can be used to integrate Buzz with other applications like OBS Studio.
When enabled, live text transcripts will be exported to a text file as they get generated and translated.

If AI translation is enabled for live recordings, the translated text will also be exported to the text file.
Filename for the translated text will end with `.translated.txt`.

### Live transcription mode

Three transcription modes are available:

**Append below** - New sentences will be added below existing with an empty space between them.
Last sentence will be at the bottom.

**Append above** - New sentences will be added above existing with an empty space between them.
Last sentence will be at the top.

**Append and correct** - New sentences will be added at the end of existing transcript without extra spaces between.
This mode will also try to correct errors at the end of previously transcribed sentences. This mode requires more
processing power and more powerful hardware to work.

## Advanced Preferences

To keep preferences section simple for new users, some more advanced preferences are settable via OS environment variables. Set the necessary environment variables in your OS before starting Buzz or create a script to set them.

On MacOS and Linux crete `run_buzz.sh` with the following content:

```bash
#!/bin/bash
export VARIABLE=value
export SOME_OTHER_VARIABLE=some_other_value
buzz
```

On Windows crete `run_buzz.bat` with the following content:

```bat
@echo off
set VARIABLE=value
set SOME_OTHER_VARIABLE=some_other_value
"C:\Program Files (x86)\Buzz\Buzz.exe"
```

Alternatively you can set environment variables in your OS settings. See [this guide](https://phoenixnap.com/kb/windows-set-environment-variable#ftoc-heading-4) or [this video](https://www.youtube.com/watch?v=bEroNNzqlF4) more information.

### Available variables

**BUZZ_WHISPERCPP_N_THREADS** - Number of threads to use for Whisper.cpp model. Default is `4`.

On a laptop with 16 threads setting `BUZZ_WHISPERCPP_N_THREADS=8` leads to some 15% speedup in transcription time.
Increasing number of threads even more will lead in slower transcription time as results from parallel threads has to be
combined to produce the final answer.

**BUZZ_TRANSLATION_API_BASE_URL** - Base URL of OpenAI compatible API to use for translation.

**BUZZ_TRANSLATION_API_KEY** - Api key of OpenAI compatible API to use for translation.

**BUZZ_MODEL_ROOT** - Root directory to store model files.
Defaults to [user_cache_dir](https://pypi.org/project/platformdirs/).

**BUZZ_FAVORITE_LANGUAGES** - Coma separated list of supported language codes to show on top of language list.

**BUZZ_DOWNLOAD_COOKIEFILE** - Location of a [cookiefile](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) to use for downloading private videos or as workaround for anti-bot protection.

**BUZZ_FORCE_CPU** - Will force Buzz to use CPU and not GPU, useful for setups with older GPU if that is slower than GPU or GPU has issues. Example usage `BUZZ_FORCE_CPU=true`. Available since `1.2.1`

**BUZZ_MERGE_REGROUP_RULE** - Custom regroup merge rule to use when combining transcripts with word-level timings. More information on available options [in stable-ts repo](https://github.com/jianfch/stable-ts?tab=readme-ov-file#regrouping-methods). Available since `1.3.0`
