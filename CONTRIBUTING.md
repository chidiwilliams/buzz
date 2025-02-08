# Buzz Contribution Guide

## Internationalization

To contribute a new language translation to Buzz:

1. Run `make translation_po locale=[locale]`. `[locale]` is a string with the format "language\[_script\]\[_country\]",
   where:

    - "language" is a lowercase, two-letter ISO 639 language code,
    - "script" is a titlecase, four-letter, ISO 15924 script code, and
    - "country" is an uppercase, two-letter, ISO 3166 country code.

   For example: `make translation_po locale=en_US`.

2. Fill in the translations in the `.po` file generated in `locale/[locale]/LC_MESSAGES`.
3. Run `make translation_mo` to compile the translations, then test your changes.
4. Create a new pull request with your changes.

## Troubleshooting

If you encounter any issues, please open an issue on the Buzz GitHub repository. Here are a few tips to gather data about the issue, so it is easier for us to fix.

**Provide details**

What version of the Buzz are you using? On what OS? What are steps to reproduce it? What settings were selected, like what model type and size was used.

**Logs**

Log files contain valuable information about what the Buzz was doing before the issue occurred. You can get the logs like this:
* Mac and Linux run the app from the terminal and check the output.
* Windows paste this into the Windows Explorer address bar `%USERPROFILE%\AppData\Local\Buzz\Buzz\Logs` and check the logs file.

**Test on latest version**

To see if your issue has already been fixed, try running the latest version of the Buzz. To get it log in to the GitHub and go to [Actions section](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml?query=branch%3Amain). Latest development versions attached to Artifacts section of successful builds. 

Linux versions get also pushed to the snap. To install latest development version use `snap install buzz --channel latest/edge`



## Running Buzz locally

### Linux (Ubuntu)

1. Clone the repository `git clone --recursive https://github.com/chidiwilliams/buzz.git`
2. Enter repo folder `cd buzz`
3. Install Poetry `pipx install poetry`
4. Activate the virtual environment `poetry shell`
5. Install the dependencies `poetry install`
6. Install system dependencies you may be missing 
```
sudo apt-get install --no-install-recommends libyaml-dev libtbb-dev libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 libxcb-cursor0 libportaudio2 gettext libpulse0 ffmpeg
```
On versions prior to Ubuntu 24.04 install `sudo apt-get install --no-install-recommends libegl1-mesa`
7. Build Buzz `poetry build`
8. Run Buzz `python -m buzz`

#### Necessary dependencies for Faster Whisper on GPU

   All the dependencies for GPU support should be included in the dependency packages already installed, 
   but if you get issues running Faster Whisper on GPU, install [CUDA 12](https://developer.nvidia.com/cuda-downloads), [cuBLASS](https://developer.nvidia.com/cublas) and [cuDNN](https://developer.nvidia.com/cudnn).

#### Error for Faster Whisper on GPU `Could not load library libcudnn_ops_infer.so.8`

   You need to add path to the library to the `LD_LIBRARY_PATH` environment variable.
   Check exact path to your poetry virtual environment, it may be different for you.

```
  export LD_LIBRARY_PATH=/home/PutYourUserNameHere/.cache/pypoetry/virtualenvs/buzz-captions-JjGFxAW6-py3.12/lib/python3.12/site-packages/nvidia/cudnn/lib/:$LD_LIBRARY_PATH
```


### Mac

1. Clone the repository `git clone --recursive https://github.com/chidiwilliams/buzz.git`
2. Enter repo folder `cd buzz`
3. Install Poetry `brew install poetry`
4. Activate the virtual environment `poetry shell`
5. Install the dependencies `poetry install`
6. Install system dependencies you may be missing `brew install ffmpeg`
7. Build Buzz `poetry build`
8. Run Buzz `python -m buzz`



### Windows

Assumes you have [Git](https://git-scm.com/downloads) and [python](https://www.python.org/downloads) installed and added to PATH.

1. Install the chocolatey package manager for Windows. [More info](https://docs.chocolatey.org/en-us/choco/setup)
```
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```
2. Install the GNU make. `choco install make`
3. Install the ffmpeg. `choco install ffmpeg`
4. Install [MSYS2](https://www.msys2.org/), follow [this guide](https://sajidifti.medium.com/how-to-install-gcc-and-gdb-on-windows-using-msys2-tutorial-0fceb7e66454).
5. Install Poetry, paste this info Windows PowerShell line by line. [More info](https://python-poetry.org/docs/)
```
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

[Environment]::SetEnvironmentVariable("Path", $env:Path + ";%APPDATA%\pypoetry\venv\Scripts", "User")

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
6. Add poetry to PATH. `%APPDATA%\Python\Scripts`
7. Restart Windows.
8. Clone the repository `git clone --recursive https://github.com/chidiwilliams/buzz.git`
9. Enter repo folder `cd buzz`
10. Activate the virtual environment `poetry shell`
11. Install the dependencies `poetry install`
12. `cp -r .\dll_backup\ .\buzz\`
13. Build Buzz `poetry build`
14. Run Buzz `python -m buzz`

#### GPU Support

GPU support on Windows with Nvidia GPUs is included out of the box in the `.exe` installer. 

To add GPU support for source or `pip` installed version first ensure CUDA 12.1 is installed - https://developer.nvidia.com/cuda-12-1-0-download-archive 
Other versions of CUDA 12 should also work.

Switch torch library to GPU version. It must match the CUDA version installed, see https://pytorch.org/get-started/locally/ .
```
pip3 uninstall torch torchaudio  
pip3 install torch==2.2.1+cu121 torchaudio==2.2.1+cu121 --index-url https://download.pytorch.org/whl/cu121
```

To use Faster Whisper on GPU, install the following libraries:
* [cuBLAS](https://developer.nvidia.com/cublas)
* [cuDNN](https://developer.nvidia.com/cudnn)

Ensure ffmpeg dependencies are installed
```
pip3 uninstall ffmpeg ffmpeg-python  
pip3 install ffmpeg
pip3 install ffmpeg-python
```

Run Buzz `python -m buzz`