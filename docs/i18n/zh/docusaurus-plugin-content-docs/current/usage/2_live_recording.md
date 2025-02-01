---
title: 实时录制
---

若要开始实时录制，请按以下步骤操作：

- 选择录制任务、语言、质量和麦克风。
- 点击“录制”。

> **注意：** 使用默认的 Whisper 模型转录音频会占用大量系统资源。若想实现实时性能，可考虑使用 Whisper.cpp Tiny 模型。

| 字段   | 选项                                                                                                      | 默认值           | 描述                                                                                                                                                                                                                                                                                    |
| ------ | --------------------------------------------------------------------------------------------------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 任务   | "转录"、"翻译"                                                                                            | "转录"           | "转录"会将输入音频转换为所选语言的文本，而"翻译"则会将其转换为英文文本。                                                                                                                                                                                                                |
| 语言   | 完整的支持语言列表请参阅 [Whisper 文档](https://github.com/openai/whisper#available-models-and-languages) | "自动检测语言"   | "自动检测语言"会根据音频的前几秒尝试检测其中的语言。不过，如果已知音频语言，建议手动选择，因为在很多情况下这可以提高转录质量。                                                                                                                                                          |
| 质量   | "极低"、"低"、"中"、"高"                                                                                  | "极低"           | 转录质量决定了用于转录的 Whisper 模型。"极低"使用"tiny"模型；"低"使用"base"模型；"中"使用"small"模型；"高"使用"medium"模型。模型越大，转录质量越高，但所需的系统资源也越多。更多关于模型的信息请参阅 [Whisper 文档](https://github.com/openai/whisper#available-models-and-languages)。 |
| 麦克风 | [系统可用麦克风]                                                                                          | [系统默认麦克风] | 用于录制输入音频的麦克风。                                                                                                                                                                                                                                                              |

[![Buzz 实时录制](https://cdn.loom.com/sessions/thumbnails/564b753eb4d44b55b985b8abd26b55f7-with-play.gif)](https://www.loom.com/share/564b753eb4d44b55b985b8abd26b55f7 "Live Recording on Buzz")

### 录制电脑播放的音频（macOS）

若要录制电脑应用程序播放的音频，你可以安装一个音频回环驱动程序（一种可让你创建虚拟音频设备的程序）。本指南后续将介绍在 Mac 上使用 [BlackHole](https://github.com/ExistentialAudio/BlackHole) 的方法，但你也可以根据自己的操作系统选择其他替代方案（例如 [LoopBeAudio](https://nerds.de/en/loopbeaudio.html)、[LoopBack](https://rogueamoeba.com/loopback/) 和 [Virtual Audio Cable](https://vac.muzychenko.net/en/)）。

1. [通过 Homebrew 安装 BlackHole](https://github.com/ExistentialAudio/BlackHole#option-2-install-via-homebrew)

   ```shell
   brew install blackhole-2ch
   ```

### 2. 通过聚焦搜索（Spotlight）或直接打开 `/Applications/Utilities/Audio Midi Setup.app` 来启动“音频 MIDI 设置”。

![通过聚焦搜索打开音频MIDI设置](https://existential.audio/howto/img/spotlight.png)

### 3. 点击窗口左下角的“+”图标，然后选择“创建多输出设备”。

![创建多输出设备](https://existential.audio/howto/img/createmulti-output.png)

### 4. 将你的默认扬声器和 BlackHole 添加到这个多输出设备中。

![多输出设备截图](https://existential.audio/howto/img/multi-output.png)

### 5. 将此多输出设备设置为你的扬声器（可在应用程序内或系统全局进行设置），这样音频就会被输送到 BlackHole 中。

### 6. 打开 Buzz 软件，选择 BlackHole 作为录音的麦克风，接着像平常一样进行录制，你就能看到通过 BlackHole 播放的音频的转录文本了。

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
