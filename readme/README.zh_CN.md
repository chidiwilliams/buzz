[[English](../README.md)] <- Click here to View the English page.

# Buzz

[项目文档](https://chidiwilliams.github.io/buzz/zh/docs)

在个人电脑上离线转录和翻译音频。技术模型来源 OpenAI [Whisper](https://github.com/openai/whisper).

![MIT License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml/badge.svg)](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/chidiwilliams/buzz/branch/main/graph/badge.svg?token=YJSB8S2VEP)](https://codecov.io/github/chidiwilliams/buzz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/chidiwilliams/buzz)
[![Github all releases](https://img.shields.io/github/downloads/chidiwilliams/buzz/total.svg)](https://GitHub.com/chidiwilliams/buzz/releases/)

![Buzz](https://raw.githubusercontent.com/chidiwilliams/buzz/refs/heads/main/buzz/assets/buzz-banner.jpg)

## 功能特性

- 转录音视频文件或 YouTube 链接
- 麦克风实时音频转录
  - 演示窗口，方便活动和演讲时使用
- 转录前语音分离，提升嘈杂音频的准确性
- 转录媒体中的说话人识别
- 支持多种 Whisper 后端
  - 支持 Nvidia GPU 的 CUDA 加速
  - 支持 Mac Apple Silicon
  - 支持 Whisper.cpp 在大多数 GPU（含集成显卡）上的 Vulkan 加速
- 通过 Huggingface 支持多种 Transformer 模型系列
- 导出转录文本为 TXT、SRT 和 VTT 格式
- 高级转录查看器，支持搜索、播放控制和速度调节
- 高效导航的键盘快捷键
- 监听文件夹，自动转录新文件
- 支持脚本和自动化的命令行界面
- 插件系统，含 AI 摘要生成和自动转录调整等插件

## 安装

### macOS

从 [SourceForge](https://sourceforge.net/projects/buzz-captions/files/) 下载 `.dmg` 文件。

### Windows

从 [SourceForge](https://sourceforge.net/projects/buzz-captions/files/) 下载安装文件。

应用程序未获得签名，安装时会收到警告弹窗。选择 `更多信息` -> `仍然运行`。

### Linux

Buzz 可通过 [Flatpak](https://flathub.org/apps/io.github.chidiwilliams.Buzz) 或 [Snap](https://snapcraft.io/buzz) 安装。

安装 Flatpak：
```shell
flatpak install flathub io.github.chidiwilliams.Buzz
```

[![Download on Flathub](https://flathub.org/api/badge?svg&locale=en)](https://flathub.org/en/apps/io.github.chidiwilliams.Buzz)

安装 Snap：
```shell
sudo apt-get install libportaudio2 libcanberra-gtk-module libcanberra-gtk3-module
sudo snap install buzz
```

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/buzz)

### PyPI

安装 [ffmpeg](https://www.ffmpeg.org/download.html)

确保使用 Python 3.12 环境。

安装 Buzz：

```shell
pip install buzz-captions
python -m buzz
```

**PyPI 版本的 GPU 支持**

如需在 Windows 上为 Nvidia GPU 启用 GPU 支持，请为 PyPI 安装版本确保 [torch](https://pytorch.org/get-started/locally/) 的 CUDA 支持：

```
pip3 install -U torch==2.8.0+cu129 torchaudio==2.8.0+cu129 --index-url https://download.pytorch.org/whl/cu129
pip3 install nvidia-cublas-cu12==12.9.1.4 nvidia-cuda-cupti-cu12==12.9.79 nvidia-cuda-runtime-cu12==12.9.79 --extra-index-url https://pypi.nvidia.com
```

### 最新开发版本

有关如何获取具有最新功能和错误修复的最新开发版本，请查阅 [FAQ](https://chidiwilliams.github.io/buzz/docs/faq#9-where-can-i-get-latest-development-version)。

### 支持 Buzz

您可以通过给仓库点亮 🌟 Star 并分享给朋友来支持 Buzz。

### 截图

<div style="display: flex; flex-wrap: wrap;">
    <img alt="导入文件" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-1-import.png" style="max-width: 18%; margin-right: 1%;" />
    <img alt="主界面" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-2-main_screen.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="偏好设置" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-3-preferences.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="模型偏好" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-3.2-model-preferences.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="转录文本" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-4-transcript.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="实时录音" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-5-live_recording.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="调整大小" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-6-resize.png" style="max-width: 18%;" />
</div>
