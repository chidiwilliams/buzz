# Windows support for Demucs

## Installation and usage

If you don't have much experience with Anaconda, python or the shell, here are more detailed instructions. Note that **Demucs is not supported on 32bits systems** (as Pytorch is not available there).

- First install Anaconda with **Python 3.8** or more recent, which you can find [here][install].
- Start the [Anaconda prompt][prompt].

Then, all commands that follow must be run from this prompt.

<details>
  <summary>I have no coding experience and these are too difficult for me</summary>

> Then a GUI is suitable for you. See [Demucs GUI](https://github.com/CarlGao4/Demucs-Gui)

</details>

### If you want to use your GPU

If you have graphic cards produced by NVIDIA with more than 2GiB of memory, you can separate tracks with GPU acceleration. To achieve this, you must install Pytorch with CUDA. If Pytorch was already installed (you already installed Demucs for instance), first run  `python.exe -m pip uninstall torch torchaudio`.
Then visit [Pytorch Home Page](https://pytorch.org/get-started/locally/) and follow the guide on it to install with CUDA support. Please make sure that the version of torchaudio should no greater than 2.1 (which is the latest version when this document is written, but 2.2.0 is sure unsupported)

### Installation

Start the Anaconda prompt, and run the following

```cmd
conda install -c conda-forge ffmpeg
python.exe -m pip install -U demucs SoundFile
```

### Upgrade

To upgrade Demucs, simply run `python.exe -m pip install -U demucs`, from the Anaconda prompt.

### Usage

Then to use Demucs, just start the **Anaconda prompt** and run:
```
demucs -d cpu "PATH_TO_AUDIO_FILE_1" ["PATH_TO_AUDIO_FILE_2" ...]
```
The `"` around the filename are required if the path contains spaces. A simple way to input these paths is draging a file from a folder into the terminal.

To find out the separated files, you can run this command and open the folders:
```
explorer separated
```

### Separating an entire folder

You can use the following command to separate an entire folder of mp3s for instance (replace the extension `.mp3` if needs be for other file types)
```
cd FOLDER
for %i in (*.mp3) do (demucs -d cpu "%i")
```

## Potential errors

If you have an error saying that `mkl_intel_thread.dll` cannot be found, you can try to first run
`conda install -c defaults intel-openmp -f`. Then try again to run the `demucs` command. If it still doesn't work, you can try to run first `set CONDA_DLL_SEARCH_MODIFICATION_ENABLE=1`, then again the `demucs` command and hopefully it will work 🙏.

**If you get a permission error**, please try starting the Anaconda Prompt as administrator.


[install]: https://www.anaconda.com/download
[prompt]: https://docs.anaconda.com/anaconda/user-guide/getting-started/#open-prompt-win
