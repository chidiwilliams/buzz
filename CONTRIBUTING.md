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
3. Create virtual environment `python -m venv venv` (needs to be done only the first time)
4. Add fix for nvidia cudnn library path to the virtual environment
```
echo 'export LD_LIBRARY_PATH="$VIRTUAL_ENV/lib/python3.12/site-packages/nvidia/cudnn/lib:$LD_LIBRARY_PATH"' >> venv/bin/activate
```
5. Activate the virtual environment `source venv/bin/activate`
6. Install Poetry `pip install poetry`
7. Install the dependencies `poetry install`
8. Install system dependencies you may be missing 
```
sudo apt-get install --no-install-recommends libyaml-dev libtbb-dev libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 libxcb-cursor0 libportaudio2 gettext libpulse0 ffmpeg
```
On versions prior to Ubuntu 24.04 install `sudo apt-get install --no-install-recommends libegl1-mesa`
8. Build Buzz `poetry build`
9. Run Buzz `python -m buzz`

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
3. Create virtual environment `python -m venv venv` (needs to be done only the first time)
4. Activate the virtual environment `source venv/bin/activate`
5. Install Poetry `pip install poetry`
6. Install the dependencies `poetry install`
7. Install system dependencies you may be missing `brew install ffmpeg`
8. Build Buzz `poetry build`
9. Run Buzz `python -m buzz`



### Windows

Assumes you have [Git](https://git-scm.com/downloads) and [python](https://www.python.org/downloads) installed and added to PATH.

1. Install the chocolatey package manager for Windows. [More info](https://docs.chocolatey.org/en-us/choco/setup)
```
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```
2. Install the GNU make. `choco install make`
3. Install the ffmpeg. `choco install ffmpeg`
4. Install [MSYS2](https://www.msys2.org/), follow [this guide](https://sajidifti.medium.com/how-to-install-gcc-and-gdb-on-windows-using-msys2-tutorial-0fceb7e66454).
5. Clone the repository `git clone --recursive https://github.com/chidiwilliams/buzz.git`
6. Enter repo folder `cd buzz`
7. Create virtual environment `python -m venv venv` (needs to be done only the first time)
8. Activate the virtual environment `.\venv\Scripts\activate`
9. Install Poetry `pip install poetry`
10. Install the dependencies `poetry install`
11. `cp -r .\dll_backup\ .\buzz\`
12. Build Buzz `poetry build`
13. Run Buzz `python -m buzz`

Note: It should be safe to ignore any "syntax errors" you see during the build. Buzz will work. Also you can ignore any errors for FFmpeg. Buzz tries to load FFmpeg by several different means and some of them throw errors, but FFmpeg should eventually be found and work. 

#### GPU Support

GPU support on Windows with Nvidia GPUs is included out of the box in the `.exe` installer. 

To add GPU support for source or `pip` installed version switch torch library to GPU version. For more info see https://pytorch.org/get-started/locally/ .
```
poetry source add --priority=supplemental torch https://download.pytorch.org/whl/cu124
poetry source add --priority=supplemental nvidia https://pypi.ngc.nvidia.com

poetry add torch==2.6.0+cu124 torchaudio==2.6.0+cu124
poetry add nvidia-cublas-cu12==12.4.5.8 nvidia-cuda-cupti-cu12==12.4.127 nvidia-cuda-nvrtc-cu12==12.4.127 nvidia-cuda-runtime-cu12==12.4.127 nvidia-cufft-cu12==11.2.1.3 nvidia-curand-cu12==10.3.5.147 nvidia-cusolver-cu12==11.6.1.9 nvidia-cusparse-cu12==12.3.1.170 nvidia-nvtx-cu12==12.4.127
```

To use Faster Whisper on GPU, install the following libraries:
* [cuBLAS](https://developer.nvidia.com/cublas)
* [cuDNN](https://developer.nvidia.com/cudnn)

If you run into issues with FFmpeg, ensure ffmpeg dependencies are installed
```
pip3 uninstall ffmpeg ffmpeg-python  
pip3 install ffmpeg
pip3 install ffmpeg-python
```

Run Buzz `python -m buzz`