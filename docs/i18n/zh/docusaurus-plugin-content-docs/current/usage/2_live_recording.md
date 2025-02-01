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

[![Buzz 实时录制](https://cdn.loom.com/sessions/thumbnails/564b753eb4d44b55b985b8abd26b55f7-with-play.gif)](https://www.loom.com/share/564b753eb4d44b55b985b8abd26b55f7 "在Buzz 上实时转录")

### 录制电脑播放的音频（macOS）

若要录制电脑应用程序播放的音频，你可以安装一个音频回环驱动程序（一种可让你创建虚拟音频设备的程序）。本指南后续将介绍在 Mac 上使用 [BlackHole](https://github.com/ExistentialAudio/BlackHole) 的方法，但你也可以根据自己的操作系统选择其他替代方案（例如 [LoopBeAudio](https://nerds.de/en/loopbeaudio.html)、[LoopBack](https://rogueamoeba.com/loopback/) 和 [Virtual Audio Cable](https://vac.muzychenko.net/en/)）。

1. [通过 Homebrew 安装 BlackHole](https://github.com/ExistentialAudio/BlackHole#option-2-install-via-homebrew)

   ```shell
   brew install blackhole-2ch
   ```

2. 通过聚焦搜索（Spotlight）或直接打开 `/Applications/Utilities/Audio Midi Setup.app` 来启动“音频 MIDI 设置”。

![通过聚焦搜索打开音频MIDI设置](https://existential.audio/howto/img/spotlight.png)

3. 点击窗口左下角的“+”图标，然后选择“创建多输出设备”。

![创建多输出设备](https://existential.audio/howto/img/createmulti-output.png)

4. 将你的默认扬声器和 BlackHole 添加到这个多输出设备中。

![多输出设备截图](https://existential.audio/howto/img/multi-output.png)

5. 将此多输出设备设置为你的扬声器（可在应用程序内或系统全局进行设置），这样音频就会被输送到 BlackHole 中。

6. 打开 Buzz 软件，选择 BlackHole 作为录音的麦克风，接着像平常一样进行录制，你就能看到通过 BlackHole 播放的音频的转录文本了。

### 录制电脑播放的音频（Windows）

若要转录系统音频，你需要配置虚拟音频设备，并将你想要转录的应用程序的音频输出连接到该虚拟扬声器。之后，你就可以在 Buzz 中选择它作为音频源。

1. 安装 [VB CABLE](https://vb - audio.com/Cable/) 作为虚拟音频设备。
2. 使用 Windows 声音设置进行配置。右键单击系统托盘里的扬声器图标，然后选择“打开声音设置”。在“选择你的输出设备”下拉菜单中，选择“CABLE Input”，将所有系统声音发送到虚拟设备；或者使用“高级声音选项”，选择要将声音输出到该设备的应用程序。

### 录制电脑播放的音频（Linux）

正如 [Ubuntu 维基](https://wiki.ubuntu.com/record_system_sound?uselang=zh) 中所述，在任何使用 PulseAudio 的 Linux 系统上，你可以将应用程序的音频重定向到虚拟扬声器。之后，你可以在 Buzz 中选择它作为音频源。

总体步骤如下：

1. 启动会产生你想要转录的声音的应用程序，并开始播放。例如，在媒体播放器中播放视频。
2. 启动 Buzz 并打开实时录制界面，以便查看设置。
3. 在 PulseAudio 音量控制（`pavucontrol`）的“录制”选项卡中，配置从你想要转录声音的应用程序到 Buzz 的声音路由。
