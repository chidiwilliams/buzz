---
title: 介绍
sidebar_position: 1
---

在您的个人电脑上离线转录和翻译音频。由 OpenAI 的 [Whisper](https://github.com/openai/whisper) 提供支持。

![MIT License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml/badge.svg)](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/chidiwilliams/buzz/branch/main/graph/badge.svg?token=YJSB8S2VEP)](https://codecov.io/github/chidiwilliams/buzz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/chidiwilliams/buzz)
[![Github all releases](https://img.shields.io/github/downloads/chidiwilliams/buzz/total.svg)](https://GitHub.com/chidiwilliams/buzz/releases/)

<blockquote>
<p>在 App Store 下载运行的性能更佳。 获得外观更整洁、音频播放、拖放导入、转录编辑、搜索等功能的原生Mac版本。</p>
<a href="https://apps.apple.com/cn/app/buzz-captions/id6446018936?mt=12&amp;itsct=apps_box_badge&amp;itscg=30200"><img src="https://toolbox.marketingtools.apple.com/api/badges/download-on-the-mac-app-store/black/zh-cn?size=250x83" alt="在 Mac App Store 下载" /></a>
</blockquote>

## 功能

- 导入音频和视频文件，并将转录内容导出为 TXT、SRT 和 VTT 格式（[演示](https://www.loom.com/share/cf263b099ac3481082bb56d19b7c87fe)）
- 从电脑麦克风转录和翻译为文本（资源密集型，可能无法实时完成，[演示](https://www.loom.com/share/564b753eb4d44b55b985b8abd26b55f7)）
- 支持 [Whisper](https://github.com/openai/whisper#available-models-and-languages)、
  [Whisper.cpp](https://github.com/ggerganov/whisper.cpp)、[Faster Whisper](https://github.com/guillaumekln/faster-whisper)、
  [Whisper 兼容的 Hugging Face 模型](https://huggingface.co/models?other=whisper) 和
  [OpenAI Whisper API](https://platform.openai.com/docs/api-reference/introduction)
- [命令行界面](#命令行界面)
- 支持 Mac、Windows 和 Linux
