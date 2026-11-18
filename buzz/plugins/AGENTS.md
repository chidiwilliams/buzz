# Buzz Plugin System — Guide for Agents

This document explains how the Buzz plugin system works and how to create new
plugins. Read it fully before adding or modifying a plugin.

## Overview

Plugins extend the transcription pipeline without modifying Buzz's core. A
plugin is a **folder** containing a `plugin.py` entry module that defines exactly
one subclass of `BuzzPlugin`. Plugins can:

- Process / replace the **source audio** before transcription.
- Modify or replace the **transcription result** (segments) after transcription.
- Run **custom code** and import parts of Buzz.
- Declare **pip dependencies** that get installed into the user cache on load.
- Expose **configuration** fields (text, multi-line text, checkbox, password)
  shown in a generated settings dialog.
- Provide **localized** names/descriptions/labels.

### Where plugins live

- Bundled plugins ship in `buzz/plugins/<plugin_id>/` (this directory). They are
  copied into the user-writable folder on first launch — see
  `loader.BUNDLED_PLUGIN_IDS` and `loader.copy_bundled_plugins()`.
- Installed plugins live in `<user_cache_dir>/Buzz/plugins/<plugin_id>/`.
- Plugin dependencies install into `<user_cache_dir>/Buzz/plugins_deps/` which is
  added to `sys.path`.

Users manage plugins from **Help → Plugins**: add by URL (a `.zip`),
enable/disable, reorder execution, edit settings.

## Architecture (key files)

- `base.py` — the plugin contract: `BuzzPlugin`, `PluginMetadata`, `ConfigField`,
  `ConfigFieldType`, `PluginContext`, and `plugin_gettext` (localization).
- `loader.py` — discovery, zip download/extract, dynamic import, bundled-copy.
- `manager.py` — `PluginManager`: registry, enable/order/config persistence,
  dependency install, hook dispatch.
- `post_processing.py` — runs post-transcription hooks off the UI thread and
  marshals DB access back to the main thread.

## The plugin contract

A plugin subclasses `BuzzPlugin` and sets a `metadata` class attribute. All hooks
are optional; defaults are no-ops.

```python
from buzz.plugins.base import (
    BuzzPlugin, PluginMetadata, ConfigField, ConfigFieldType,
    PluginContext, plugin_gettext,
)

_ = plugin_gettext(__file__)  # localized strings, see "Localization" below


class MyPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="my_plugin",                 # stable, unique; matches the folder name
        name=_("My Plugin"),
        description=_("What this plugin does."),
        version="1.0.0",
        pip_dependencies=[],            # e.g. ["python-docx>=1.1"]
        config_fields=[
            ConfigField(key="api_key", label=_("API key"),
                        type=ConfigFieldType.PASSWORD),
            ConfigField(key="enabled_flag", label=_("Some flag"),
                        type=ConfigFieldType.BOOL, default=True),
        ],
    )

    def before_transcription(self, task, context: PluginContext):
        # Runs on the WORKER thread. May process the audio at task.file_path.
        # Return a new file path to use, or None to leave it unchanged.
        # Do NOT touch the database or Qt here.
        return None

    def after_transcription(self, task, segments, context: PluginContext):
        # Runs on a BACKGROUND thread. Return the (possibly modified) list of
        # Segment objects. Return `segments` unchanged to do nothing.
        return segments

    def on_complete(self, transcription_id, task, segments, context: PluginContext):
        # Runs on a BACKGROUND thread AFTER the transcription is saved.
        # Use for side effects keyed on the persisted transcription, e.g.
        # writing notes or exporting a file.
        return None
```

### Hooks and when they run

| Hook                   | Thread       | Purpose                                            |
|------------------------|--------------|----------------------------------------------------|
| `check_skip`           | worker       | Return `list[Segment]` to skip transcription entirely, or `None` to proceed. Runs after `before_transcription`. DB access via `context.transcription_service` is safe (marshaled to main thread). |
| `before_transcription` | worker       | Process/replace source audio; return new file path |
| `after_transcription`  | background   | Modify/replace result `Segment`s before save       |
| `on_complete`          | background   | Post-save side effects (notes, file export, upload)|

Hooks run for **enabled** plugins in the user-defined **order**. Exceptions in a
hook are logged and never break the pipeline or other plugins.

### `PluginContext`

Passed to every hook. Fields:

- `context.config` — resolved config dict keyed by `ConfigField.key` (includes
  password values pulled from the keyring; missing values fall back to defaults).
- `context.transcription_service` — DB access. **Safe to call from background
  hooks**: calls are automatically marshaled to the main thread (the DB
  connection is thread-affine). Useful methods:
  `update_transcription_notes(id, text)`,
  `replace_transcription_segments(id, segments)`,
  `get_transcription_segments(transcription_id=id)`.
- `context.settings` — the Buzz `Settings` object.
- `context.log` — a `logging.Logger` namespaced to the plugin.

### Data types

- `task` is a `FileTranscriptionTask` (see `buzz/transcriber/transcriber.py`):
  `file_path`, `original_file_path`, `uid`, `transcription_options`, etc.
- `segments` is a `list[Segment]`; `Segment(start, end, text, translation="")`
  with `start`/`end` in **milliseconds**.

### Segment metadata

Each `Segment` has a `metadata` list of `dict[str, str]`. In `after_transcription`,
append a dict to a segment's `metadata` to attach information to that row
without changing or deleting its text:

```python
segment.metadata.append({"review_reason": "Possible repetition loop", "confidence": "0.21"})
```

- It is saved as JSON in the `transcription_segment.metadata` column and read
  back by `get_transcription_segments`.
- The transcription viewer shows every key-value pair as a `key: value` line in
  the row's tooltip, so use keys and values a user can read.
- Use strings. Other values are shown with `str()`, and nested structures are
  not rendered in a useful way.
- Append, never replace the list: other plugins may have added entries to the
  same segment.
- Metadata only survives while the same `Segment` objects are passed along.
  Code that builds new `Segment(...)` objects (e.g. the Resize Transcript plugin,
  the viewer's resize tool, speaker identification) starts them with empty
  metadata. If your plugin regroups segments, copy the metadata across;
  if it reads other plugins' metadata, it must run after them in the plugin order.

## Metadata cache

Transcription engines and speaker identification produce more data than Buzz
saves as segments: token and word probabilities, `no_speech_prob`,
`avg_logprob`, detected language probabilities, diarization turns, and so on.
Buzz keeps that data per transcription in JSON files that plugins can read:

```
<user_cache_dir>/Buzz/metadata/<transcription id>/<name>.json
```

The transcription id is `task.uid` / the `transcription_id` passed to
`on_complete`. Use `buzz.metadata_cache` rather than building paths:

```python
from buzz import metadata_cache

def after_transcription(self, task, segments, context):
    result = metadata_cache.load_metadata(task.uid, metadata_cache.FASTER_WHISPER)
    if result is None:          # another engine, or the save failed
        return segments
    for whisper_segment in result["segments"]:
        if whisper_segment["no_speech_prob"] > 0.6:
            ...
    return segments
```

- `load_metadata(id, name)` returns the parsed JSON, or `None` if there is no
  such file. `list_metadata(id)` returns the names a transcription has.
  `metadata_path(id, name)` gives the file path.
- `save_metadata(id, name, data)` lets a plugin keep its own data next to Buzz's.
  Use a name prefixed with your plugin id (`my_plugin_scores`), so it never
  clashes with the names below. Names may contain letters, digits, `_`, `-`
  and `.`. It converts dataclasses, numpy values and similar to JSON; infinite
  and NaN floats become `null`. It logs and returns `None` on failure, never raises.
- The files are written by the transcriber, so they exist in
  `after_transcription` and `on_complete`, but **not** in
  `before_transcription` or `check_skip`.
- Only the file of the engine that ran is there. A transcription run before
  this feature, or a failed save, has no files. Always handle `None`.
- Times in engine files are the engine's own (mostly seconds), not the
  milliseconds of `Segment`. Engine files describe the raw transcription, so
  they don't reflect what `after_transcription` plugins or the user changed later.
- The folder is deleted with the transcription, cleared when it is restarted,
  and copied when a transcription is copied (e.g. Resize, Speaker
  Identification), so a copy can read the result of its source.

### Available metadata

| Name (`metadata_cache.*`)  | Written by | Content |
|----------------------------|------------|---------|
| `whisper_cpp` (`WHISPER_CPP`) | Whisper.cpp | The `--output-json-full` output of `whisper-cli`, byte for byte: `result.language`, `params`, and `transcription[]` with `offsets` (ms), `text` and `tokens[]` (`text`, `id`, `p` probability, `t_dtw`, `offsets`). See the note below. |
| `faster_whisper` (`FASTER_WHISPER`) | Faster Whisper | `{"info": {...}, "segments": [...]}`. `info` has `language`, `language_probability`, `duration`, `duration_after_vad`, `all_language_probs`, `transcription_options`, `vad_options`. Each segment has `id`, `seek`, `start`, `end` (s), `text`, `tokens`, `avg_logprob`, `compression_ratio`, `no_speech_prob`, `temperature`, and `words[]` (`start`, `end`, `word`, `probability`) when word-level timings are on. |
| `openai_whisper` (`OPENAI_WHISPER`) | Whisper | The result of `model.transcribe()`: `text`, `language`, `segments[]` with `id`, `seek`, `start`, `end` (s), `text`, `tokens`, `temperature`, `avg_logprob`, `compression_ratio`, `no_speech_prob`. With word-level timings it is stable-ts's `WhisperResult.to_dict()`, whose segments also have `words[]` with `probability`. |
| `hugging_face` (`HUGGING_FACE`) | Hugging Face | The result of Buzz's `TransformersTranscriber.transcribe()`: `text` and `segments[]` with `start`, `end` (s), `text`. Few models return more than that. |
| `openai_api` (`OPENAI_API`) | OpenAI API (and compatible servers) | `{"model": ..., "responses": [{"offset_ms": ..., "response": {...}}]}`, one response per uploaded chunk (files over 25 MB are split). `offset_ms` is where the chunk starts in the file. A `verbose_json` response has `language`, `duration`, `segments[]` with `avg_logprob`, `compression_ratio`, `no_speech_prob`, `tokens`, and `words[]`; `gpt-4o` models return only `text`. |
| `speaker_identification` (`SPEAKER_IDENTIFICATION`) | Speaker identification | See below. |

**whisper_cpp text encoding.** whisper-cli can split one multi-byte character
across tokens, so the file is not always valid UTF-8. Read it as Latin-1 and
recover the text of a field the way Buzz does:

```python
import json
with open(metadata_cache.metadata_path(task.uid, metadata_cache.WHISPER_CPP), encoding="latin-1") as f:
    result = json.load(f)
text = result["transcription"][0]["text"].encode("latin-1").decode("utf-8", errors="replace")
```

`load_metadata` reads files as UTF-8 and so raises `UnicodeDecodeError` on such
a file; use the snippet above for `whisper_cpp`.

**speaker_identification** is saved when speaker identification succeeds:
on the transcript it ran on when it runs in the viewer (and again as the user
renames speakers there), on the new transcript when the user saves the result,
or on the transcription itself for folder watch / CLI transcriptions with
"Identify speakers" on. The viewer shows the saved result when its speaker
identification dialog is opened again; a new run replaces it. It has:

- `diarizer` (`"msdd"` or `"sortformer"`), `num_speakers` (requested count or
  `null`), `language`.
- `speaker_turns[]` — `start_time`, `end_time` (ms), `speaker` (`"Speaker 0"`, ...):
  who speaks when, from the diarizer.
- `word_timestamps[]` — `text`, `start`, `end` (**seconds**), `score` (mean log
  probability of the word's letters in forced alignment; `null` for words that
  could not be aligned and were spread over their window), and
  `joins_previous` on pieces of a long word that was split for alignment.
- `word_speaker_mapping[]` — `word`, `start_time`, `end_time` (ms), `speaker`.
- `sentences[]` — `speaker`, `start_time`, `end_time` (ms), `text`: the result
  the segments are built from.
- `speaker_names` — the names the user gave in the viewer, e.g.
  `{"Speaker 0": "Alice", "Speaker 1": "Speaker 1"}` (`{}` for folder watch),
  and `merge_speaker_sentences`.

When adding a new engine or data source, save its data with
`metadata_cache.save_metadata(task.uid, ...)` in the transcriber, add a name
constant to `buzz/metadata_cache.py`, and document it in this table.

## Configuration fields

Declare config via `ConfigField`. Types (`ConfigFieldType`):

- `TEXT` — single-line input.
- `TEXTAREA` — multi-line input.
- `BOOL` — checkbox.
- `PASSWORD` — masked input with a show/hide toggle. **Stored in the OS keyring**,
  never in plain settings.

Each field has `key`, `label`, optional `type`, `default`, `description`,
`placeholder`. The settings dialog is generated automatically from these. Read
values from `context.config[field.key]` in your hooks.

## Dependencies

List pip requirements in `metadata.pip_dependencies`. On first load the manager
installs them into the shared `plugins_deps` cache folder (tracked so they are
not reinstalled unnecessarily). Prefer packages already bundled with Buzz (e.g.
`openai`) and declare nothing when possible — dependency install can fail
offline. See `buzz/pip_utils.py` for how pip is invoked across environments
(frozen builds, sandboxes).

## Localization

Plugins cannot use Buzz's compiled `.mo` catalogs. Instead, call
`plugin_gettext(__file__)` to get a translator (conventionally named `_`) and
wrap user-facing strings (`name`, `description`, field `label`s, messages).

Provide translations in JSON files in a `locale/` folder next to `plugin.py`,
named by locale (`locale/lv_LV.json`) with a language-only fallback
(`locale/lv.json`). Each file maps the **English source string** to its
translation:

```json
{
  "My Plugin": "Mans spraudnis",
  "API key": "API atslēga"
}
```

The JSON **key must match the English source string exactly** (including
punctuation, parentheses and whitespace) — it is matched verbatim against the
string you passed to `_()`. Multi-line source strings assembled via implicit
string concatenation in Python collapse into a single key, so the key has no
line breaks. Strings without a translation (or when no file matches the active
locale) fall through unchanged, so a plugin works with no locale files at all.
The active locale comes from Buzz's `UI_LOCALE` setting.

> **Critical:** Never use an empty string `""` as a translation value. The
> translator treats an empty value as "no translation" and falls back to the
> English source string, but only if the value is falsy. A locale file with
> `"My Plugin": ""` will cause the plugin name to appear blank in the UI.
> Either provide a real translation or omit the key entirely.

Bundled plugins ship a translation file for **every locale Buzz supports**. The
current set (keep it in sync across all bundled plugins) is:

```
ca_ES, da_DK, de_DE, es_ES, fr, it_IT, ja_JP, lv_LV, nl,
pl_PL, pt_BR, ru, tr_TR, uk_UA, zh_CN, zh_TW
```

When adding or changing a user-facing string in a bundled plugin, update the key
in **all** of these files. See `ai_summary/locale/` or
`enhanced_language_detection/locale/` for a complete worked example, and copy the
file set from an existing plugin so the locale list stays consistent.

> **Cache note:** Bundled plugins are copied to `~/.cache/Buzz/plugins/` on
> launch. `copy_bundled_plugins()` compares each bundled plugin against its
> cached copy and refreshes the cache whenever the bundle differs — a fixed
> `plugin.py`, or an added/updated/removed locale file. So editing a bundled
> plugin's code or locales and relaunching Buzz is enough; no manual sync is
> needed. (Build artifacts like `__pycache__`/`*.pyc` are ignored in the
> comparison.) User-installed plugins are never touched.

## Packaging & distribution

A distributable plugin is a `.zip` whose contents are the plugin folder. The
archive may have `plugin.py` at the root or inside a single wrapping directory
(GitHub-style zips work). Users install it via **Help → Plugins → Add by URL**.

Layout:

```
my_plugin/
  plugin.py            # required: defines one BuzzPlugin subclass
  locale/              # optional: <locale>.json translation files
    lv_LV.json
```

## Checklist for creating a plugin

1. Create `buzz/plugins/<plugin_id>/plugin.py` with one `BuzzPlugin` subclass.
2. Set `metadata` with a unique `id` (match the folder name), `name`,
   `description`, and any `config_fields`.
3. Implement only the hooks you need; respect the thread rules above.
4. Use `plugin_gettext(__file__)` for user-facing strings; add `locale/*.json`
   (for bundled plugins, provide all locales listed under **Localization** and
   keep the keys matching the English source strings exactly).
5. Keep `pip_dependencies` minimal; reuse bundled packages.
6. To ship it bundled: add the id to `loader.BUNDLED_PLUGIN_IDS` and add the
   folder to `Buzz.spec` `datas` (e.g. `("buzz/plugins/<id>", "plugins/<id>")`).
7. Add tests under `tests/plugins/` (see `plugin_system_test.py`).

## Reference: the `ai_summary` plugin

`ai_summary/plugin.py` is the shipped reference plugin. It uses `on_complete` to
summarize the transcript via an OpenAI-compatible API and writes the result to
the Notes field and/or a file. It demonstrates password config, localization, and
reusing the bundled `openai` client (no extra dependencies).
