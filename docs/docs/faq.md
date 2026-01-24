---
title: FAQ
sidebar_position: 5
---

### 1. Where are the models stored?

The models are stored:

- Linux: `~/.cache/Buzz`
- Mac OS: `~/Library/Caches/Buzz`
- Windows: `%USERPROFILE%\AppData\Local\Buzz\Buzz\Cache`

Paste the location in your file manager to access the models or go to `Help -> Preferences -> Models` and click on `Show file location` button after downloading some model.

### 2. What can I try if the transcription runs too slowly?

Speech recognition requires large amount of computation, so one option is to try using a lower Whisper model size or using a Whisper.cpp model to run speech recognition of your computer. If you have access to a computer with GPU that has at least 6GB of VRAM you can try using the Faster Whisper model.

Buzz also supports using OpenAI API to do speech recognition on a remote server. To use this feature you need to set OpenAI API key in Preferences. See [Preferences](https://chidiwilliams.github.io/buzz/docs/preferences) section for more details.

### 3. How to record system audio?

To transcribe system audio you need to configure virtual audio device and connect output from the applications you want to transcribe to this virtual speaker. After that you can select it as source in the Buzz. See [Usage](https://chidiwilliams.github.io/buzz/docs/usage/live_recording) section for more details.

Relevant tools:

- Mac OS - [BlackHole](https://github.com/ExistentialAudio/BlackHole).
- Windows - [VB CABLE](https://vb-audio.com/Cable/)
- Linux - [PulseAudio Volume Control](https://wiki.ubuntu.com/record_system_sound)

### 4. What model should I use?

Model size to use will depend on your hardware and use case. Smaller models will work faster but will have more inaccuracies. Larger models will be more accurate but will require more powerful hardware or longer time to transcribe.

When choosing among large models consider the following. "Large" is the first released older model, "Large-V2" is later updated model with better accuracy, for some languages considered the most robust and stable. "Large-V3" is the latest model with the best accuracy in many cases, but some times can hallucinate or invent words that were never in the audio. "Turbo" model tries to get a good balance between speed and accuracy. The only sure way to know what model best suits your needs is to test them all in your language.

In addition to choosing an appropriate model size you also can choose whisper type.
- **Whisper** is initial OpenAI implementation, it is accurate but slow and requires a lot of RAM.
- **Faster Whisper** is an optimized implementation, it is orders of magnitude faster than regular Whisper and requires less RAM. Use this option if you have an Nvidia GPU with at least 6GB of VRAM.
- **Whisper.cpp** is optimized C++ implementation, it quite fast and efficient and will use any brand of GPU. Whisper.cpp is capable of running real time transcription even on a modern laptop with integrated GPU. It can also run on CPU only. Use this option if you do not have Nvidia GPU. 
- **HuggingFace** option is a `Transformers` implementation and is good in that it supports wide range of custom models that may be optimized for a particular language. This option also supports [MMS](https://ai.meta.com/blog/multilingual-model-speech-recognition/) family of models from Meta AI that support over 1000 of worlds languages as well as [PEFT](https://github.com/huggingface/peft) adjustments to Whisper models.

### 5. How to get GPU acceleration for faster transcription?

On Linux GPU acceleration is supported out of the box on Nvidia GPUs. If you still get any issues install [CUDA 12](https://developer.nvidia.com/cuda-downloads), [cuBLASS](https://developer.nvidia.com/cublas) and [cuDNN](https://developer.nvidia.com/cudnn).

On Windows GPU support is included in the installation `.exe`. CUDA 12 required, computers with older CUDA versions will use CPU. See [this note](https://github.com/chidiwilliams/buzz/blob/main/CONTRIBUTING.md#gpu-support) on enabling CUDA GPU support.

### 6. How to fix `Unanticipated host error[PaErrorCode-9999]`?

Check if there are any system settings preventing apps from accessing the microphone.

On Windows, see if Buzz has permission to use the microphone in Settings -> Privacy -> Microphone.

See method 1 in this video https://www.youtube.com/watch?v=eRcCYgOuSYQ

For method 2 there is no need to uninstall the antivirus, but see if you can temporarily disable it or if there are settings that may prevent Buzz from accessing the microphone.

### 7. Can I use Buzz on a computer without internet?

Yes, Buzz can be used without internet connection if you download the necessary models on some other computer that has the internet and manually move them to the offline computer. The easiest way to find where the models are stored is to go to Help -> Preferences -> Models. Then download some model, and push "Show file location" button. This will open the folder where the models are stored. Copy the models folder to the same location on the offline computer. F.e. for Linux it is `.cache/Buzz/models` in your home directory.

### 8. Buzz crashes, what to do?

If a model download was incomplete or corrupted, Buzz may crash. Try to delete the downloaded model files in `Help -> Preferences -> Models` and re-download them.

If that does not help, check the log file for errors and [report the issue](https://github.com/chidiwilliams/buzz/issues) so we can fix it. If possible attach the log file to the issue. Since Version `1.3.4`, to get to the logs folder go to `Help -> About Buzz` and click on `Show logs` button.

### 9. Where can I get latest development version?

Latest development version will have latest bug fixes and most recent features. If you feel a bit adventurous it is recommended to try the latest development version as they needs some testing before they get released to everybody.

- **Linux** users can get the latest version with this command `sudo snap install buzz --edge`

- **For other** platforms do the following:
  1. Go to the [build section](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml?query=branch%3Amain)
  2. Click on the link to the latest build, the most recent successful build entry in the list
  3. Scroll down to the artifacts section in the build page
  4. Download the installation file. Please note that you need to be logged in the Github to see the download links.
  ![Latest build example](https://chidiwilliams.github.io/buzz/img/latest-development-build.jpeg "Latest build example")

### 10. Why is my system theme not applied to Buzz installed from Flatpak?
 
For dark themes on Gnome environments you may need to install `gnome-themes-extra` package and set the following preferences:
```
gsettings set org.gnome.desktop.interface gtk-theme Adwaita-dark
gsettings set org.gnome.desktop.interface color-scheme prefer-dark
```

If your system theme is not applied to Buzz installed from Flatpak Linux app store, ensure the desired theme is in `~/.themes` folder.

You may need to copy the system themes to this folder `cp -r /usr/share/themes/ ~/.themes/` and give Flatpaks access to this folder `flatpak override --user --filesystem=~/.themes`.

On Fedora run the following to install the necessary packages 
`sudo dnf install gnome-themes-extra qadwaitadecorations-qt{5,6} qt{5,6}-qtwayland`