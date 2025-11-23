# Linux support for Demucs

If your distribution has at least Python 3.8, and you just wish to separate
tracks with Demucs, not train it, you can just run

```bash
pip3 install --user -U demucs
# Then anytime you want to use demucs, just do
python3 -m demucs -d cpu PATH_TO_AUDIO_FILE_1
# If you have added the user specific pip bin/ folder to your path, you can also do
demucs -d cpu PATH_TO_AUDIO_FILE_1
```

If Python is too old, or you want to be able to train, I recommend [installing Miniconda][miniconda], with Python 3.8 or more.

```bash
conda activate
pip3 install -U demucs
# Then anytime you want to use demucs, first do conda activate, then
demucs -d cpu PATH_TO_AUDIO_FILE_1
```

Of course, you can also use a specific env for Demucs.

**Important, torchaudio 0.12 update:** Torchaudio no longer supports decoding mp3s without ffmpeg installed. You must have ffmpeg installed, either through Anaconda (`conda install ffmpeg -c conda-forge`) or as a distribution package (e.g. `sudo apt-get install ffmpeg`).


[miniconda]: https://docs.conda.io/en/latest/miniconda.html#linux-installers
