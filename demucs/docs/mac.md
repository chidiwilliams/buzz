# macOS support for Demucs

If you have a sufficiently recent version of macOS, you can just run

```bash
python3 -m pip install --user -U demucs
# Then anytime you want to use demucs, just do
python3 -m demucs -d cpu PATH_TO_AUDIO_FILE_1
# If you have added the user specific pip bin/ folder to your path, you can also do
demucs -d cpu PATH_TO_AUDIO_FILE_1
```

If you do not already have Anaconda installed or much experience with the terminal on macOS, here are some detailed instructions:

1. Download [Anaconda 3.8 (or more recent) 64-bit for macOS][anaconda]:
2. Open [Anaconda Prompt in macOS][prompt]
3. Follow these commands:
```bash
conda activate
pip3 install -U demucs
# Then anytime you want to use demucs, first do conda activate, then
demucs -d cpu PATH_TO_AUDIO_FILE_1
```

**Important, torchaudio 0.12 update:** Torchaudio no longer supports decoding mp3s without ffmpeg installed. You must have ffmpeg installed, either through Anaconda (`conda install ffmpeg -c conda-forge`) or with Homebrew for instance (`brew install ffmpeg`).

[anaconda]:  https://www.anaconda.com/download
[prompt]: https://docs.anaconda.com/anaconda/user-guide/getting-started/#open-nav-mac
