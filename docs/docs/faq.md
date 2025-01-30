---
title: FAQ
sidebar_position: 5
---

### 1. Where are the models stored?

The models are stored:

- Linux: `~/.cache/Buzz`
- Mac OS: `~/Library/Caches/Buzz`
- Windows: `%USERPROFILE%\AppData\Local\Buzz\Buzz\Cache`

Paste the location in your file manager to access the models.

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

### 5. How to get GPU acceleration for faster transcription?

On Linux GPU acceleration is supported out of the box on Nvidia GPUs. If you still get any issues install [CUDA 12](https://developer.nvidia.com/cuda-downloads), [cuBLASS](https://developer.nvidia.com/cublas) and [cuDNN](https://developer.nvidia.com/cudnn).

On Windows see [this note](https://github.com/chidiwilliams/buzz/blob/main/CONTRIBUTING.md#gpu-support) on enabling CUDA GPU support.

For Faster whisper CUDA 12 is required, computers with older CUDA versions will use CPU.

### 6. How to fix `Unanticipated host error[PaErrorCode-9999]`?

Check if there are any system settings preventing apps from accessing the microphone.

On Windows, see if Buzz has permission to use the microphone in Settings -> Privacy -> Microphone.

See method 1 in this video https://www.youtube.com/watch?v=eRcCYgOuSYQ

For method 2 there is no need to uninstall the antivirus, but see if you can temporarily disable it or if there are settings that may prevent Buzz from accessing the microphone.

### 7. Can I use Buzz on a computer without internet?

Yes, Buzz can be used without internet connection if you download the necessary models on some other computer that has the internet and manually move them to the offline computer. The easiest way to find where the models are stored is to go to Help -> Preferences -> Models. Then download some model, and push "Show file location" button. This will open the folder where the models are stored. Copy the models folder to the same location on the offline computer. F.e. for Linux it is `.cache/Buzz/models` in your home directory.

### 8. Buzz crashes, what to do?

If a model download was incomplete or corrupted, Buzz may crash. Try to delete the downloaded model files in `Help -> Preferences -> Models` and re-download them.

If that does not help, check the log file for errors and [report the issue](https://github.com/chidiwilliams/buzz/issues) so we can fix it. The log file is located in `~/Library/Logs/Buzz` (Mac OS) or `%USERPROFILE%\AppData\Local\Buzz\Buzz\Logs` (Windows). On Linux run the Buzz from the command line to see the relevant messages.

### 9. Where can I get latest development version?

Latest development version will have latest bug fixes and most recent features. If you feel a bit adventurous it is recommended to try the latest development version as they needs some testing before they get released to everybody.

- **Linux** users can get the latest version with this command `sudo snap install buzz --edge`

- **For other** platforms do the following:
  1. Go to the [build section](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml?query=branch%3Amain)
  2. Click on the link to the latest build
  3. Scroll down to the artifacts section in the build page
  4. Download the installation file. Please note that you need to be logged in the Github to see the download links.
