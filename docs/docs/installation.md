---
title: Installation
sidebar_position: 2
---

To install Buzz, download the [latest version](https://github.com/chidiwilliams/buzz/releases/latest) for your operating
system. Buzz is available on **Mac** (Intel), **Windows**, and **Linux**. (For Apple Silicon, please see
the [App Store version](https://apps.apple.com/us/app/buzz-captions/id6446018936?mt=12&itsct=apps_box_badge&itscg=30200).)

## macOS (Intel, macOS 11.7 and later)

Install via [brew](https://brew.sh/):

```shell
brew install --cask buzz
```

Alternatively, download and run the `Buzz-x.y.z.dmg` file.

For Mac Silicon (and for a better experience on Mac Intel),
download [Buzz Captions](https://apps.apple.com/us/app/buzz-captions/id6446018936?mt=12&amp;itsct=apps_box_badge&amp;itscg=30200)
on the App Store.

## Windows (Windows 10 and later)

Download and run the `Buzz-x.y.z.exe` file.

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

Then, download and extract the `Buzz-x.y.z-unix.tar.gz` file

## PyPI

```shell
pip install buzz-captions
python -m buzz
```
