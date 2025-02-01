---
title: CLI
sidebar_position: 5
---

## Commands

### `add`

Start a new transcription task.

```
Usage: buzz add [options] [file url file...]

Options:
  -t, --task <task>              The task to perform. Allowed: translate,
                                 transcribe. Default: transcribe.
  -m, --model-type <model-type>  Model type. Allowed: whisper, whispercpp,
                                 huggingface, fasterwhisper, openaiapi. Default:
                                 whisper.
  -s, --model-size <model-size>  Model size. Use only when --model-type is
                                 whisper, whispercpp, or fasterwhisper. Allowed:
                                 tiny, base, small, medium, large. Default:
                                 tiny.
  --hfid <id>                    Hugging Face model ID. Use only when
                                 --model-type is huggingface. Example:
                                 "openai/whisper-tiny"
  -l, --language <code>          Language code. Allowed: af (Afrikaans), am
                                 (Amharic), ar (Arabic), as (Assamese), az
                                 (Azerbaijani), ba (Bashkir), be (Belarusian),
                                 bg (Bulgarian), bn (Bengali), bo (Tibetan), br
                                 (Breton), bs (Bosnian), ca (Catalan), cs
                                 (Czech), cy (Welsh), da (Danish), de (German),
                                 el (Greek), en (English), es (Spanish), et
                                 (Estonian), eu (Basque), fa (Persian), fi
                                 (Finnish), fo (Faroese), fr (French), gl
                                 (Galician), gu (Gujarati), ha (Hausa), haw
                                 (Hawaiian), he (Hebrew), hi (Hindi), hr
                                 (Croatian), ht (Haitian Creole), hu
                                 (Hungarian), hy (Armenian), id (Indonesian), is
                                 (Icelandic), it (Italian), ja (Japanese), jw
                                 (Javanese), ka (Georgian), kk (Kazakh), km
                                 (Khmer), kn (Kannada), ko (Korean), la (Latin),
                                 lb (Luxembourgish), ln (Lingala), lo (Lao), lt
                                 (Lithuanian), lv (Latvian), mg (Malagasy), mi
                                 (Maori), mk (Macedonian), ml (Malayalam), mn
                                 (Mongolian), mr (Marathi), ms (Malay), mt
                                 (Maltese), my (Myanmar), ne (Nepali), nl
                                 (Dutch), nn (Nynorsk), no (Norwegian), oc
                                 (Occitan), pa (Punjabi), pl (Polish), ps
                                 (Pashto), pt (Portuguese), ro (Romanian), ru
                                 (Russian), sa (Sanskrit), sd (Sindhi), si
                                 (Sinhala), sk (Slovak), sl (Slovenian), sn
                                 (Shona), so (Somali), sq (Albanian), sr
                                 (Serbian), su (Sundanese), sv (Swedish), sw
                                 (Swahili), ta (Tamil), te (Telugu), tg (Tajik),
                                 th (Thai), tk (Turkmen), tl (Tagalog), tr
                                 (Turkish), tt (Tatar), uk (Ukrainian), ur
                                 (Urdu), uz (Uzbek), vi (Vietnamese), yi
                                 (Yiddish), yo (Yoruba), zh (Chinese). Leave
                                 empty to detect language.
  -p, --prompt <prompt>          Initial prompt.
  -w, --word-timestamps         Generate word-level timestamps. (available since 1.2.0)
  --openai-token <token>         OpenAI access token. Use only when
                                 --model-type is openaiapi. Defaults to your
                                 previously saved access token, if one exists.
  --srt                          Output result in an SRT file.
  --vtt                          Output result in a VTT file.
  --txt                          Output result in a TXT file.
  --hide-gui                     Hide the main application window. (available since 1.2.0)
  -h, --help                     Displays help on commandline options.
  --help-all                     Displays help including Qt specific options.
  -v, --version                  Displays version information.

Arguments:
  files or urls                  Input file paths or urls. Url import availalbe since 1.2.0.
```

**Examples**:

```shell
# Translate two MP3 files from French to English using OpenAI Whisper API
buzz add --task translate --language fr --model-type openaiapi /Users/user/Downloads/1b3b03e4-8db5-ea2c-ace5-b71ff32e3304.mp3 /Users/user/Downloads/koaf9083k1lkpsfdi0.mp3

# Transcribe an MP4 using Whisper.cpp "small" model and immediately export to SRT and VTT files
buzz add --task transcribe --model-type whispercpp --model-size small --prompt "My initial prompt" --srt --vtt /Users/user/Downloads/buzz/1b3b03e4-8db5-ea2c-ace5-b71ff32e3304.mp4
```
