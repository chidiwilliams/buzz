[[简体中文](readme/README.zh_CN.md)] <- 点击查看中文页面。

# Buzz

[Documentation](https://chidiwilliams.github.io/buzz/)

Transcribe and translate audio offline on your personal computer. Powered by
OpenAI's [Whisper](https://github.com/openai/whisper).

![MIT License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml/badge.svg)](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/chidiwilliams/buzz/branch/main/graph/badge.svg?token=YJSB8S2VEP)](https://codecov.io/github/chidiwilliams/buzz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/chidiwilliams/buzz)
[![Github all releases](https://img.shields.io/github/downloads/chidiwilliams/buzz/total.svg)](https://GitHub.com/chidiwilliams/buzz/releases/)

![Buzz](./buzz/assets/buzz-banner.jpg)

## Features
- Transcribe audio and video files or Youtube links
- Live realtime audio transcription from microphone
  - Presentation window for easy accessibility during events and presentations
- Speech separation before transcription for better accuracy on noisy audio
- Speaker identification in transcribed media
- Multiple whisper backend support
  - CUDA acceleration support for Nvidia GPUs
  - Apple Silicon support for Macs
  - Vulkan acceleration support for Whisper.cpp on most GPUs, including integrated GPUs
- Export transcripts to TXT, SRT, and VTT
- Advanced Transcription Viewer with search, playback controls, and speed adjustment
- Keyboard shortcuts for efficient navigation
- Watch folder for automatic transcription of new files
- Command-Line Interface for scripting and automation

## Installation

### macOS

Download the `.dmg` from the [SourceForge](https://sourceforge.net/projects/buzz-captions/files/).

### Windows

Get the installation files from the [SourceForge](https://sourceforge.net/projects/buzz-captions/files/).

App is not signed, you will get a warning when you install it. Select `More info` -> `Run anyway`.

**Alternatively, install with [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/)**

```shell
winget install ChidiWilliams.Buzz
```

### Linux

Buzz is available as a [Flatpak](https://flathub.org/apps/io.github.chidiwilliams.Buzz) or a [Snap](https://snapcraft.io/buzz). 

To install flatpak, run:
```shell
flatpak install flathub io.github.chidiwilliams.Buzz
```

[![Download on Flathub](https://flathub.org/api/badge?svg&locale=en)](https://flathub.org/en/apps/io.github.chidiwilliams.Buzz)

To install snap, run:
```shell
sudo apt-get install libportaudio2 libcanberra-gtk-module libcanberra-gtk3-module
sudo snap install buzz
```

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/buzz)

### PyPI

Install [ffmpeg](https://www.ffmpeg.org/download.html)

Ensure you use Python 3.12 environment.

Install Buzz

```shell
pip install buzz-captions
python -m buzz
```

**GPU support for PyPI**

To have GPU support for Nvidia GPUS on Windows, for PyPI installed version ensure, CUDA support for [torch](https://pytorch.org/get-started/locally/) 

```
pip3 install -U torch==2.8.0+cu129 torchaudio==2.8.0+cu129 --index-url https://download.pytorch.org/whl/cu129
pip3 install nvidia-cublas-cu12==12.9.1.4 nvidia-cuda-cupti-cu12==12.9.79 nvidia-cuda-runtime-cu12==12.9.79 --extra-index-url https://pypi.ngc.nvidia.com
```

### Latest development version

For info on how to get latest development version with latest features and bug fixes see [FAQ](https://chidiwilliams.github.io/buzz/docs/faq#9-where-can-i-get-latest-development-version).

### Screenshots

<div style="display: flex; flex-wrap: wrap;">
    <img alt="File import" src="share/screenshots/buzz-1-import.png" style="max-width: 18%; margin-right: 1%;" />
    <img alt="Main screen" src="share/screenshots/buzz-2-main_screen.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Preferences" src="share/screenshots/buzz-3-preferences.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Model preferences" src="share/screenshots/buzz-3.2-model-preferences.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Transcript" src="share/screenshots/buzz-4-transcript.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Live recording" src="share/screenshots/buzz-5-live_recording.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Resize" src="share/screenshots/buzz-6-resize.png" style="max-width: 18%;" />
</div>

