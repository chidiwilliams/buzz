---
title: 偏好设置
sidebar_position: 4
---

从菜单栏打开偏好设置窗口，或点击 `Ctrl/Cmd + ,`。

## 常规偏好设置

### OpenAI API 偏好设置

**API 密钥** - 用于验证 OpenAI API 请求的密钥。要获取 OpenAI 的 API 密钥，请参阅 [此文章](https://help.openai.com/en/articles/4936850-where-do-i-find-my-openai-api-key)。

**基础 URL** - 默认情况下，所有请求都会发送到 OpenAI 公司提供的 API。他们的 API URL 是 `https://api.openai.com/v1/`。其他公司也提供了兼容的 API。你可以在 [讨论页面](https://github.com/chidiwilliams/buzz/discussions/827) 找到可用的 API URL 列表。

### 默认导出文件名

设置文件识别的默认导出文件名。例如，值为 `{{ input_file_name }} ({{ task }}d on {{ date_time }})` 时，TXT 导出文件将默认保存为`Input Filename (transcribed on 19-Sep-2023 20-39-25).txt`（输入文件名 (转录于 19-Sep-2023 20-39-25).txt）。

可用变量：

| 键                | 描述                                  | 示例                                                       |
| ----------------- | ------------------------------------- | ---------------------------------------------------------- |
| `input_file_name` | 导入文件的文件名                      | `audio`（例如，如果导入的文件路径是 `/path/to/audio.wav`） |
| `task`            | 转录任务                              | `transcribe`, `translate`                                  |
| `language`        | 语言代码                              | `en`, `fr`, `yo` 等                                        |
| `model_type`      | 模型类型                              | `Whisper`, `Whisper.cpp`, `Faster Whisper` 等              |
| `model_size`      | 模型大小                              | `tiny`, `base`, `small`, `medium`, `large` 等              |
| `date_time`       | 导出时间（格式：`%d-%b-%Y %H-%M-%S`） | `19-Sep-2023 20-39-25`                                     |

### 实时识别导出

实时识别导出可用于将 Buzz 与其他应用程序（如 OBS Studio）集成。  
启用后，实时文本识别将在生成和翻译时导出到文本文件。

如果为实时录音启用了 AI 翻译，翻译后的文本也将导出到文本文件。  
翻译文本的文件名将以 `.translated.txt` 结尾。

### 实时识别模式

有三种转识别式可用：

**下方追加** - 新句子将在现有内容下方添加，并在它们之间留有空行。最后一句话将位于底部。

**上方追加** - 新句子将在现有内容上方添加，并在它们之间留有空行。最后一句话将位于顶部。

**追加并修正** - 新句子将在现有转录内容的末尾添加，中间不留空行。此模式还会尝试修正之前转录句子末尾的错误。此模式需要更多的处理能力和更强大的硬件支持。

## 高级偏好设置

为了简化新用户的偏好设置部分，一些更高级的设置可以通过操作系统环境变量进行配置。在启动 Buzz 之前，请在操作系统中设置必要的环境变量，或创建一个脚本来设置它们。

在 MacOS 和 Linux 上，创建 `run_buzz.sh`，内容如下：

```bash
#!/bin/bash
export VARIABLE=value
export SOME_OTHER_VARIABLE=some_other_value
buzz
```

在 Windows 上，创建 `run_buzz.bat`，内容如下：

```bat
@echo off
set VARIABLE=value
set SOME_OTHER_VARIABLE=some_other_value
"C:\Program Files (x86)\Buzz\Buzz.exe"
```

或者，你可以在操作系统设置中设置环境变量。更多信息请参阅 [此指南](https://phoenixnap.com/kb/windows-set-environment-variable#ftoc-heading-4) 或 [此视频](https://www.youtube.com/watch?v=bEroNNzqlF4)。

### 可用变量

**BUZZ_WHISPERCPP_N_THREADS** - Whisper.cpp 模型使用的线程数。默认为 `4`。  
在具有 16 线程的笔记本电脑上，设置 `BUZZ_WHISPERCPP_N_THREADS=8` 可以使转录时间加快约 15%。  
进一步增加线程数会导致转录时间变慢，因为并行线程的结果需要合并以生成最终答案。

**BUZZ_TRANSLATION_API_BASE_URl** - 用于翻译的 OpenAI 兼容 API 的基础 URL。

**BUZZ_TRANSLATION_API_KEY** - 用于翻译的 OpenAI 兼容 API 的密钥。

**BUZZ_MODEL_ROOT** - 存储模型文件的根目录。  
默认为 [user_cache_dir](https://pypi.org/project/platformdirs/)。

**BUZZ_FAVORITE_LANGUAGES** - 以逗号分隔的支持语言代码列表，显示在语言列表顶部。

**BUZZ_DOWNLOAD_COOKIEFILE** - 用于下载私有视频或绕过反机器人保护的 [cookiefile](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) 的位置。

**BUZZ_FORCE_CPU** - 强制 Buzz 使用 CPU 而不是 GPU，适用于旧 GPU 较慢或 GPU 有问题的设置。示例用法：`BUZZ_FORCE_CPU=true`。自 `1.2.1` 版本起可用。

**BUZZ_MERGE_REGROUP_RULE** - 合并带有单词级时间戳的转录时使用的自定义重新分组规则。更多可用选项的信息请参阅 [stable-ts 仓库](https://github.com/jianfch/stable-ts?tab=readme-ov-file#regrouping-methods)。自 `1.3.0` 版本起可用。
