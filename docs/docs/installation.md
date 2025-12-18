---
title: Installation
sidebar_position: 2
---

To install Buzz, download the [latest version](https://github.com/chidiwilliams/buzz/releases/latest) for your operating
system. Buzz is available on **Mac** (Intel), **Windows**, and **Linux**.

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

To install snap, run:
```shell
sudo apt-get install libportaudio2 libcanberra-gtk-module libcanberra-gtk3-module
sudo snap install buzz
sudo snap connect buzz:password-manager-service
```

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/buzz)

Alternatively, on Ubuntu 20.04 and later, install the dependencies:

```shell
sudo apt-get install libportaudio2
```

## PyPI

```shell
pip install buzz-captions
python -m buzz
```
