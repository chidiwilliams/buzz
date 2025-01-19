[English](../README.md) - View the English version page.

# Buzz

[项目文档](https://chidiwilliams.github.io/buzz/) | [Buzz Captions 苹果应用商店](https://apps.apple.com/us/app/buzz-captions/id6446018936?mt=12&itsct=apps_box_badge&itscg=30200)

在您的个人电脑上离线转录和翻译音频。技术来源 OpenAI [Whisper](https://github.com/openai/whisper).

![MIT License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml/badge.svg)](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/chidiwilliams/buzz/branch/main/graph/badge.svg?token=YJSB8S2VEP)](https://codecov.io/github/chidiwilliams/buzz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/chidiwilliams/buzz)
[![Github all releases](https://img.shields.io/github/downloads/chidiwilliams/buzz/total.svg)](https://GitHub.com/chidiwilliams/buzz/releases/)

<blockquote>
<p>在 App Store 上的软件性能更佳。 获得外观更整洁、音频播放、拖放导入、转录编辑、搜索等功能的Mac原生Buzz版本。</p>
<a href="https://apps.apple.com/cn/app/buzz-captions/id6446018936?mt=12&amp;itsct=apps_box_badge&amp;itscg=30200"><img src="https://toolbox.marketingtools.apple.com/api/badges/download-on-the-mac-app-store/black/zh-cn?size=250x83" alt="Download on the Mac App Store" /></a>
</blockquote>

![Buzz](../buzz/assets/buzz-banner.jpg)

## 安装

**PyPI**:

安装 [ffmpeg](https://www.ffmpeg.org/download.html)

安装 Buzz

```shell
pip install buzz-captions
python -m buzz
```

**macOS**:

使用 [brew utility](https://brew.sh/) 安装

```shell
brew install --cask buzz
```

或下载在 [Releases ](https://github.com/chidiwilliams/buzz/releases/latest) 页面的 `.dmg` 文件并运行 .

**Windows**:

下载在 [Releases ](https://github.com/chidiwilliams/buzz/releases/latest) 页面的 `.exe` 文件并运行 .

应用程序为获得未签名，当安装时会收到警告。 选择 `更多信息` -> `Run anyway`.

**Linux**:

```shell
sudo apt-get install libportaudio2 libcanberra-gtk-module libcanberra-gtk3-module
sudo snap install buzz
sudo snap connect buzz:audio-record
sudo snap connect buzz:password-manager-service
sudo snap connect buzz:pulseaudio
sudo snap connect buzz:removable-media
```

### 最新开发者版本

有关如何获取具有最新功能和错误修复的最新开发版本的信息，请参阅 [FAQ](https://chidiwilliams.github.io/buzz/docs/faq#9-where-can-i-get-latest-development-version).
