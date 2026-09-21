---
title: Custom Whisper.cpp models
---

# Custom Whisper.cpp models

Buzz can use any number of custom [Whisper.cpp](https://github.com/ggerganov/whisper.cpp)
models in addition to the built-in ones. This is useful when you have several
fine-tuned models — for example a fast model you use by default and a more accurate
model you fall back to for difficult recordings — and want to switch between them
without re-downloading anything. This feature is available since 1.4.6.

## Adding a custom model

1. Open **Preferences → Models**.
2. Set the model **Group** to **Whisper.cpp**.
3. Enter a **name** for the model.
4. Add the model file in one of two ways:
   - **Add local model file** — choose a `ggml`/`gguf` `.bin` file that is already on
     your computer. The file is used from its current location; it is not copied.
   - **Add model from URL** — paste a download link to the model `.bin` file (for
     example the download link from a Hugging Face model page). Buzz downloads it and
     adds it.

## Selecting a model

Each custom model appears by its name in the model list in **Preferences → Models** and
in the model selector on the main transcription screen. Select the one you want to use;
switch to another at any time.

## Deleting a model

Deleting a custom model removes it from the list. If Buzz downloaded the model file, that
file is also deleted. If you added a model that was already on your computer, only the
list entry is removed — your original file is left untouched.

## Upgrading from earlier versions

Earlier versions of Buzz supported a single custom Whisper.cpp model stored as
`ggml-model-whisper-custom.bin`. If you have such a model, it continues to work: it
appears automatically in the list as **Custom Whisper.cpp Model** and is neither moved
nor re-downloaded.

## Command line

A custom model can be selected non-interactively with its id:

```
buzz add --model-type whispercpp --model-size custom --custom-model-id <id> <file>
```
