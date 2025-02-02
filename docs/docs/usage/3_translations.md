---
title: Translations
---

Default `Translation` task uses Whisper model ability to translate to English. Since version `1.0.0` Buzz supports additional AI translations to any other language.

To use translation feature you will need to configure OpenAI API key and translation settings. Set OpenAI API ket in Preferences. Buzz also supports custom locally running translation AIs that support OpenAI API. For more information on locally running AIs see [ollama](https://ollama.com/blog/openai-compatibility) or [LM Studio](https://lmstudio.ai/). For information on available custom APIs see this [discussion thread](https://github.com/chidiwilliams/buzz/discussions/827).

To configure translation for Live recordings enable it in Advances settings dialog of the Live Recording settings. Enter AI model to use and prompt with instructions for the AI on how to translate. Translation option is also available for files that already have speech recognised. Use Translate button on transcription viewer toolbar.

For AI to know how to translate enter translation instructions in the "Instructions for AI" section. In your instructions you should describe to what language you want it to translate the text to. Also, you may need to add additional instructions to not add any notes or comments as AIs tend to add them. Example instructions to translate English subtitles to Spanish:

> You are a professional translator, skilled in translating English to Spanish. You will only translate each sentence sent to you into Spanish and not add any notes or comments.

If you enable "Enable live recording transcription export" in Preferences, Live text transcripts will be exported to a text file as they get generated and translated. This file can be used to further integrate Live transcripts with other applications like OBS Studio.

Approximate cost of translation for 1 hour long audio with ChatGPT `gpt-4o` model is around $0.50.
