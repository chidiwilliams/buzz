---
title: Live Recording
---

To start a live recording:

- Select a recording task, language, quality, and microphone.
- Click Record.

> **Note:** Transcribing audio using the default Whisper model is resource-intensive. Consider using the Whisper.cpp
> Tiny model to get real-time performance.

| Field      | Options                                                                                                                                  | Default                     | Description                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|------------|------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Task       | "Transcribe", "Translate"                                                                                                                | "Transcribe"                | "Transcribe" converts the input audio into text in the selected language, while "Translate" converts it into text in English.                                                                                                                                                                                                                                                                                                                         |
| Language   | See [Whisper's documentation](https://github.com/openai/whisper#available-models-and-languages) for the full list of supported languages | "Detect Language"           | "Detect Language" will try to detect the spoken language in the audio based on the first few seconds. However, selecting a language is recommended (if known) as it will improve transcription quality in many cases.                                                                                                                                                                                                                                 |
| Quality    | "Very Low", "Low", "Medium", "High"                                                                                                      | "Very Low"                  | The transcription quality determines the Whisper model used for transcription. "Very Low" uses the "tiny" model; "Low" uses the "base" model; "Medium" uses the "small" model; and "High" uses the "medium" model. The larger models produce higher-quality transcriptions, but require more system resources. See [Whisper's documentation](https://github.com/openai/whisper#available-models-and-languages) for more information about the models. |
| Microphone | [Available system microphones]                                                                                                           | [Default system microphone] | Microphone for recording input audio.                                                                                                                                                                                                                                                                                                                                                                                                                 |

[![Live Recording on Buzz](https://cdn.loom.com/sessions/thumbnails/564b753eb4d44b55b985b8abd26b55f7-with-play.gif)](https://www.loom.com/share/564b753eb4d44b55b985b8abd26b55f7 "Live Recording on Buzz")

### Record audio playing from computer (macOS)

To record audio playing from an application on your computer, you may install an audio loopback driver (a program that
lets you create virtual audio devices). The rest of this guide will
use [BlackHole](https://github.com/ExistentialAudio/BlackHole) on Mac, but you can use other alternatives for your
operating system (
see [LoopBeAudio](https://nerds.de/en/loopbeaudio.html), [LoopBack](https://rogueamoeba.com/loopback/),
and [Virtual Audio Cable](https://vac.muzychenko.net/en/)).

1. Install [BlackHole via Homebrew](https://github.com/ExistentialAudio/BlackHole#option-2-install-via-homebrew)

   ```shell
   brew install blackhole-2ch
   ```

2. Open Audio MIDI Setup from Spotlight or from `/Applications/Utilities/Audio Midi Setup.app`.

   ![Open Audio MIDI Setup from Spotlight](https://existential.audio/howto/img/spotlight.png)

3. Click the '+' icon at the lower left corner and select 'Create Multi-Output Device'.

   ![Create multi-output device](https://existential.audio/howto/img/createmulti-output.png)

4. Add your default speaker and BlackHole to the multi-output device.

   ![Screenshot of multi-output device](https://existential.audio/howto/img/multi-output.png)

5. Select this multi-output device as your speaker (application or system-wide) to play audio into BlackHole.

6. Open Buzz, select BlackHole as your microphone, and record as before to see transcriptions from the audio playing
   through BlackHole.

### Record audio playing from computer (Windows)

To transcribe system audio you need to configure virtual audio device and connect output from the applications you whant to transcribe to this virtual speaker. After that you can select it as source in the Buzz.

1. Install [VB CABLE](https://vb-audio.com/Cable/) as virtual audio device. 

2. Configure using Windows Sound settings. Right-click on the speaker icon in the system tray and select "Open Sound settings". In the "Choose your output device" dropdown select "CABLE Input" to send all system sound to the virtual device or use "Advanced sound options" to select application that will output their sound to this device.

### Record audio playing from computer (Linux)

As described on [Ubuntu Wiki](https://wiki.ubuntu.com/record_system_sound) on any Linux with pulse audio you can redirect application audio to a virtual speaker. After that you can select it as source in Buzz.

Overall steps:
1. Launch application that will produce the sound you want to transcribe and start the playback. For example start a video in a media player. 
2. Launch Buzz and open Live recording screen, so you see the settings.
3. Configure sound routing from the application you want to transcribe sound from to Buzz in `Recording tab` of the PulseAudio Volume Control (`pavucontrol`). 