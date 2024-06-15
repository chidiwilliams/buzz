---
title: Translations
---

Latest development versions support AI translations. 

To get latest development version of the Buzz log into GitHub and get it from Artifacts section of some latest [action run](https://github.com/chidiwilliams/buzz/actions).  Linux users can get the latest version from latest snap edge channel `sudo snap install buzz --channel latest/edge`

To use translation feature you will need to configure OpenAI API key and translation settings. Set OpenAI API ket in Preferences. Buzz also supports custom locally running translation AIs that support OpenAI API. For more information on locally running AIs see [ollama](https://ollama.com/blog/openai-compatibility) or [LM Studio](https://lmstudio.ai/). 

To configure translation for Live recordings enable it in Advances settings dialog of the Live Recording settings. Enter AI model to use and prompt with instructions for the AI on how to translate. Translation option is also available for files that already have speech recognised. Use Translate button on transcription viewer toolbar.

For AI to know how to translate enter translation instructions in the "Instructions for AI" section. In your instructions you should describe to what language you want it to translate the text to. Also, you may need to add additional instructions to not add any notes or comments as AIs tend to add them. Example instructions to translate English subtitles to Spanish:

> You are a professional translator, skilled in translating English to Spanish. You will only translate each sentence sent to you into Spanish and not add any notes or comments.

If you enable "Enable live recording transcription export" in Preferences, Live text transcripts will be exported to a text file as they get generated and translated. This file can be used to further integrate Live transcripts with other applications like OBS Studio.