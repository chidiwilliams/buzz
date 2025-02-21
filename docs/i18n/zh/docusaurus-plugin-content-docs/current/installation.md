---
title: 安装
sidebar_position: 2
---

要安装 Buzz，请下载适用于您操作系统的[最新版本](https://github.com/chidiwilliams/buzz/releases/latest)。Buzz 支持 **Mac**（Intel）、**Windows** 和 **Linux** 系统。（对于 Apple Silicon 用户，请参阅 [App Store 版本](https://apps.apple.com/us/app/buzz-captions/id6446018936?mt=12&itsct=apps_box_badge&itscg=30200)。）

## macOS（Intel，macOS 11.7 及更高版本）

通过 [brew](https://brew.sh/) 安装：

```shell
brew install --cask buzz
```

或者，下载并运行 `Buzz-x.y.z.dmg` 文件。

对于 Mac Silicon 用户（以及希望在 Mac Intel 上获得更好体验的用户），  
请从 App Store 下载 [Buzz Captions](https://apps.apple.com/us/app/buzz-captions/id6446018936?mt=12&itsct=apps_box_badge&itscg=30200)。

## Windows（Windows 10 及更高版本）

下载并运行 `Buzz-x.y.z.exe` 文件。

## Linux

```shell
sudo apt-get install libportaudio2 libcanberra-gtk-module libcanberra-gtk3-module
sudo snap install buzz
sudo snap connect buzz:password-manager-service
```

[![从 Snap Store 获取](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/buzz)

或者，在 Ubuntu 20.04 及更高版本上，安装依赖项：

```shell
sudo apt-get install libportaudio2
```

然后，下载并解压 `Buzz-x.y.z-unix.tar.gz` 文件。

## PyPI

```shell
pip install buzz-captions
python -m buzz
```
