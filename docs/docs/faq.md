---
title: FAQ
sidebar_position: 5
---

1. **Where are the models stored?**

   The Whisper models are stored in `~/.cache/whisper`. The Whisper.cpp models are stored in `~/Library/Caches/Buzz`
   (Mac OS), `~/.cache/Buzz` (Unix), or `C:\Users\<username>\AppData\Local\Buzz\Buzz\Cache` (Windows).

2. **What can I try if the transcription runs too slowly?**

   Try using a lower Whisper model size or using a Whisper.cpp model.

3. **How to record system audio?**

   To transcribe system audio you need to configure virtual audio device and connect output from the applications you want to transcribe to this virtual speaker. After that you can select it as source in the Buzz. See [Usage](https://chidiwilliams.github.io/buzz/docs/usage/live_recording) section for more details.

   Relevant tools:
   - Mac OS - [BlackHole](https://github.com/ExistentialAudio/BlackHole).
   - Windows - [VB CABLE](https://vb-audio.com/Cable/)
   - Linux - [PulseAudio Volume Control](https://wiki.ubuntu.com/record_system_sound)