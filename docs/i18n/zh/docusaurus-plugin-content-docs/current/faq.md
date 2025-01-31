---
title: 常见问题（FAQ）
sidebar_position: 5
---

### 1. 模型存储在哪里？

模型存储在以下位置：

- Linux: `~/.cache/Buzz`
- Mac OS: `~/Library/Caches/Buzz`
- Windows: `%USERPROFILE%\AppData\Local\Buzz\Buzz\Cache`

将上述路径粘贴到文件管理器中即可访问模型。

### 2. 如果转录速度太慢，我可以尝试什么？

语音识别需要大量计算资源，您可以尝试使用较小的 Whisper 模型，或者使用 Whisper.cpp 模型在本地计算机上运行语音识别。如果您的计算机配备了至少 6GB VRAM 的 GPU，可以尝试使用 Faster Whisper 模型。

Buzz 还支持使用 OpenAI API 在远程服务器上进行语音识别。要使用此功能，您需要在“偏好设置”中设置 OpenAI API 密钥。详情请参见 [偏好设置](https://chidiwilliams.github.io/buzz/docs/preferences) 部分。

### 3. 如何录制系统音频？

要转录系统音频，您需要配置虚拟音频设备，并将希望转录的应用程序输出连接到该虚拟扬声器。然后，您可以在 Buzz 中选择该设备作为音源。详情请参见 [使用指南](https://chidiwilliams.github.io/buzz/docs/usage/live_recording) 部分。

相关工具：

- Mac OS - [BlackHole](https://github.com/ExistentialAudio/BlackHole)
- Windows - [VB CABLE](https://vb-audio.com/Cable/)
- Linux - [PulseAudio Volume Control](https://wiki.ubuntu.com/record_system_sound)

### 4. 我应该使用哪个模型？

选择模型大小取决于您的硬件和使用场景。较小的模型运行速度更快，但准确性较低；较大的模型更准确，但需要更强的硬件或更长的转录时间。

在选择大模型时，请参考以下信息：

- **“Large”** 是最早发布的模型
- **“Large-V2”** 是后续改进版，准确率更高，被认为是某些语言中最稳定的选择
- **“Large-V3”** 是最新版本，在许多情况下准确性最佳，但有时可能会产生错误的单词
- **“Turbo”** 模型在速度和准确性之间取得了良好平衡

最好的方法是测试所有模型，以找到最适合您语言的选项。

### 5. 如何使用 GPU 加速以提高转录速度？

- 在 **Linux** 上，Nvidia GPU 受支持，可直接使用 GPU 加速。如果遇到问题，请安装 [CUDA 12](https://developer.nvidia.com/cuda-downloads)、[cuBLAS](https://developer.nvidia.com/cublas) 和 [cuDNN](https://developer.nvidia.com/cudnn)。
- 在 **Windows** 上，请参阅[此说明](https://github.com/chidiwilliams/buzz/blob/main/CONTRIBUTING.md#gpu-support) 以启用 CUDA GPU 支持。
- **Faster Whisper** 需要 CUDA 12，使用旧版 CUDA 的计算机将默认使用 CPU。

### 6. 如何修复 `Unanticipated host error[PaErrorCode-9999]`？

请检查系统设置，确保没有阻止应用访问麦克风。

- **Windows** 用户请检查“设置 -> 隐私 -> 麦克风”，确保 Buzz 有权限使用麦克风。
- 参考此视频的 [方法 1](https://www.youtube.com/watch?v=eRcCYgOuSYQ)。
- **方法 2** 无需卸载防病毒软件，但可以尝试暂时禁用，或检查是否有相关设置阻止 Buzz 访问麦克风。

### 7. 可以在没有互联网的计算机上使用 Buzz 吗？

是的，您可以在离线计算机上使用 Buzz，但需要在另一台联网计算机上下载所需模型，并手动将其移动到离线计算机。

最简单的方法是：

1. 打开“帮助 -> 偏好设置 -> 模型”
2. 下载所需的模型
3. 点击“显示文件位置”按钮，打开存储模型的文件夹
4. 将该模型文件夹复制到离线计算机的相同位置

例如，在 Linux 上，模型存储在 `~/.cache/Buzz/models` 目录中。

### 8. Buzz 崩溃了，怎么办？

如果模型下载不完整或损坏，Buzz 可能会崩溃。尝试删除已下载的模型文件，然后重新下载。

如果问题仍然存在，请检查日志文件并[报告问题](https://github.com/chidiwilliams/buzz/issues)，以便我们修复。日志文件位置如下：

- Mac OS: `~/Library/Logs/Buzz`
- Windows: `%USERPROFILE%\AppData\Local\Buzz\Buzz\Logs`
- Linux: 在终端运行 Buzz 查看相关错误信息。

### 9. 哪里可以获取最新的开发版本？

最新的开发版本包含最新的错误修复和新功能。如果您喜欢尝试新功能，可以下载最新的开发版本进行测试。

- **Linux** 用户可以运行以下命令获取最新版本：
  ```sh
  sudo snap install buzz --edge
  ```
- **其他平台** 请按以下步骤操作：
  1. 访问 [构建页面](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml?query=branch%3Amain)
  2. 点击最新构建的链接
  3. 在构建页面向下滚动到“Artifacts”部分
  4. 下载安装文件（请注意，您需要登录 GitHub 才能看到下载链接）
