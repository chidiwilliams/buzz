---
title: File Import
---

**To import a file:**

- Click Import Media File on the File menu (or the '+' icon on the toolbar, or **Command/Ctrl + O**).
- Choose an audio or video file.
- Select a task, language, and the model settings.
- Click Run.
- When the transcription status shows 'Completed', double-click on the row (or select the row and click the '⤢' icon) to
  open the transcription.

**Available options:**

To reduce misspellings you can pass some commonly misspelled words in an `Initial prompt` that is available under `Advanced...` button. See this [guide on prompting](https://cookbook.openai.com/examples/whisper_prompting_guide#pass-names-in-the-prompt-to-prevent-misspellings).  


| Field              | Options             | Default | Description                                                                                                                                                                                                                          |
| ------------------ | ------------------- | ------- |--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Export As          | "TXT", "SRT", "VTT" | "TXT"   | Export file format                                                                                                                                                                                                                   |
| Word-Level Timings | Off / On            | Off     | If checked, the transcription will generate a separate subtitle line for each word in the audio. Combine words into subtitles afterwards with the [resize option](https://chidiwilliams.github.io/buzz/docs/usage/edit_and_resize).  |
| Extract speech     | Off / On            | Off     | If checked, speech will be extracted to a separate audio tack to improve accuracy.                                                                                                                             |

(See the [Live Recording section](https://chidiwilliams.github.io/buzz/docs/usage/live_recording) for more information about the task, language, and quality settings.)

[![Media File Import on Buzz](https://cdn.loom.com/sessions/thumbnails/cf263b099ac3481082bb56d19b7c87fe-with-play.gif)](https://www.loom.com/share/cf263b099ac3481082bb56d19b7c87fe "Media File Import on Buzz")

**💡 Tip:** It is recommended to always select language to transcribe to as automatic language detection may result in unexpected results.

### Orukeet

For local multilingual transcription, choose **Hugging Face**, enter
[`oruk/orukeet`](https://huggingface.co/oruk/orukeet), and select **Transcribe**.
Buzz uses the model's Transformers export through its existing Parakeet TDT
backend. The first run downloads the weights and configuration from Hugging Face;
the required `config.json` participates in its normal model download statistics.
Subsequent runs reuse Buzz's model cache, and transcription stays on your machine.

Orukeet detects its language automatically across 25 supported languages; the
language selector does not force its decoder. Translation, initial prompts and
word-level timings are not supported. Subtitle segments use Buzz's 30-second
chunk boundaries rather than word-aligned timestamps. CUDA is used when available;
otherwise this backend runs on CPU, including on macOS.

The weights are licensed under CC BY-SA 4.0 with NVIDIA attribution. See the
[model card](https://huggingface.co/oruk/orukeet) for supported languages, evaluation
results and license details.
