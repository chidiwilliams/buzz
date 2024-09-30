# Buzz

[Documentation](https://chidiwilliams.github.io/buzz/) | [Buzz Captions on the App Store](https://apps.apple.com/us/app/buzz-captions/id6446018936?mt=12&itsct=apps_box_badge&itscg=30200)

Transcribe and translate audio offline on your personal computer. Powered by
OpenAI's [Whisper](https://github.com/openai/whisper).

![MIT License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml/badge.svg)](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/chidiwilliams/buzz/branch/main/graph/badge.svg?token=YJSB8S2VEP)](https://codecov.io/github/chidiwilliams/buzz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/chidiwilliams/buzz)
[![Github all releases](https://img.shields.io/github/downloads/chidiwilliams/buzz/total.svg)](https://GitHub.com/chidiwilliams/buzz/releases/)

<blockquote>
<p>Buzz is better on the App Store. Get a Mac-native version of Buzz with a cleaner look, audio playback, drag-and-drop import, transcript editing, search, and much more.</p>
<a href="https://apps.apple.com/us/app/buzz-captions/id6446018936?mt=12&amp;itsct=apps_box_badge&amp;itscg=30200"><img src="https://tools.applemediaservices.com/api/badges/download-on-the-mac-app-store/black/en-us?size=250x83&amp;releaseDate=1679529600" alt="Download on the Mac App Store" /></a>
</blockquote>

![Buzz](./buzz/assets/buzz-banner.jpg)

## Installation

**PyPI**:

Install [ffmpeg](https://www.ffmpeg.org/download.html)

Install Buzz
```shell
pip install buzz-captions
python -m buzz
```

**macOS**:

Install with [brew utility](https://brew.sh/)

```shell
brew install --cask buzz
```

Or download the `.dmg` from the [releases page](https://github.com/chidiwilliams/buzz/releases/latest).

**Windows**:

Download and run the `.exe` from the [releases page](https://github.com/chidiwilliams/buzz/releases/latest).

App is not signed, you will get a warning when you install it, run it anyway.

**Linux**:

```shell
sudo apt-get install libportaudio2 libcanberra-gtk-module libcanberra-gtk3-module
sudo snap install buzz
sudo snap connect buzz:audio-record
sudo snap connect buzz:password-manager-service
sudo snap connect buzz:pulseaudio
sudo snap connect buzz:removable-media
```
