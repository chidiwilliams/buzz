---
title: Installation
sidebar_position: 2
---

To install Buzz, download the latest version for your operating
system. Buzz is available on **Mac** (Intel and Apple silicon), **Windows**, and **Linux**.

### macOS

Download the `.dmg` from the [SourceForge](https://sourceforge.net/projects/buzz-captions/files/).

### Windows

Get the installation files from the [SourceForge](https://sourceforge.net/projects/buzz-captions/files/).

App is not signed, you will get a warning when you install it. Select `More info` -> `Run anyway`.

## Linux

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
sudo snap connect buzz:password-manager-service
```

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/buzz)

## PyPI

```shell
pip install buzz-captions
python -m buzz
```

On Linux install system dependencies you may be missing
```
sudo apt-get install --no-install-recommends libyaml-dev libtbb-dev libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 libxcb-cursor0 libportaudio2 gettext libpulse0 ffmpeg
```
On versions prior to Ubuntu 24.04 install `sudo apt-get install --no-install-recommends libegl1-mesa`
