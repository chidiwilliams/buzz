---
title: Preferences
sidebar_position: 4
---

Open the Preferences window from the Menu bar, or click `Ctrl/Cmd + ,`.

## General Preferences

### OpenAI API preferences

**API Key** - key to authenticate your requests to OpenAI API. To get API key from OpenAI see [this article](https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key). 

**Base Url** - By default all requests are sent to API provided by OpenAI company. Their api url is `https://api.openai.com/v1/`. Compatible APIs are also provided by other companies. List of available API urls you can find on [discussion page](https://github.com/chidiwilliams/buzz/discussions/827)

### Default export file name

Sets the default export file name for file transcriptions. For
example, a value of `{{ input_file_name }} ({{ task }}d on {{ date_time }})` will save TXT exports
as `Input Filename (transcribed on 19-Sep-2023 20-39-25).txt` by default.

Available variables:

| Key               | Description                               | Example                                                        |
|-------------------|-------------------------------------------|----------------------------------------------------------------|
| `input_file_name` | File name of the imported file            | `audio` (e.g. if the imported file path was `/path/to/audio.wav` |
| `task`            | Transcription task                        | `transcribe`, `translate`                                      |
| `language`        | Language code                             | `en`, `fr`, `yo`, etc.                                         |
| `model_type`      | Model type                                | `Whisper`, `Whisper.cpp`, `Faster Whisper`, etc.               |
| `model_size`      | Model size                                | `tiny`, `base`, `small`, `medium`, `large`, etc.               |
| `date_time`       | Export time (format: `%d-%b-%Y %H-%M-%S`) | `19-Sep-2023 20-39-25`                                         |

### Live transcript exports

Live transcription export can be used to integrate Buzz with other applications like OBS Studio. When enabled, live text transcripts will be exported to a text file as they get generated and translated.

If AI translation is enabled for live recordings, the translated text will also be exported to the text file. Filename for the translated text will end with `.translated.txt`. 