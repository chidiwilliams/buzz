@echo off
set PATH=D:\Tools\Make\bin;D:\Tools\CMake\bin;D:\Tools\FFmpeg\ffmpeg-8.1.1-full_build\bin;D:\Tools;C:\VulkanSDK\1.4.341.1\Bin;%PATH%
set VULKAN_SDK=C:\VulkanSDK\1.4.341.1

echo Initializing VS Dev Environment...
call "D:\VSBuildTools\VC\Auxiliary\Build\vcvars64.bat"

echo Syncing uv dependencies...
D:\Tools\uv.exe sync

echo Adding Nvidia GPU support...
D:\Tools\uv.exe pip install --index https://download.pytorch.org/whl/cu128 torch==2.7.1+cu128 torchaudio==2.7.1+cu128
D:\Tools\uv.exe pip install --index https://pypi.ngc.nvidia.com nvidia-cublas-cu12==12.8.3.14 nvidia-cuda-cupti-cu12==12.8.57 nvidia-cuda-nvrtc-cu12==12.8.61 nvidia-cuda-runtime-cu12==12.8.57 nvidia-cudnn-cu12==9.7.1.26 nvidia-cufft-cu12==11.3.3.41 nvidia-curand-cu12==10.3.9.55 nvidia-cusolver-cu12==11.7.2.55 nvidia-cusparse-cu12==12.5.4.2 nvidia-cusparselt-cu12==0.6.3 nvidia-nvjitlink-cu12==12.8.61 nvidia-nvtx-cu12==12.8.55

echo Building whisper_cpp explicitly...
cmake -S whisper.cpp -B whisper.cpp/build/ -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DCMAKE_INSTALL_RPATH="$$ORIGIN" -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON -DCMAKE_C_FLAGS="-D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR"  -DCMAKE_CXX_FLAGS="-D_DISABLE_CONSTEXPR_MUTEX_CONSTRUCTOR" -DCMAKE_C_COMPILER_WORKS=TRUE -DCMAKE_CXX_COMPILER_WORKS=TRUE -DGGML_VULKAN=1 -DGGML_NATIVE=OFF
cmake --build whisper.cpp/build -j --config Release --verbose

if not exist buzz\whisper_cpp mkdir buzz\whisper_cpp
copy /Y whisper.cpp\build\bin\Release\whisper-cli.exe buzz\whisper_cpp\
copy /Y whisper.cpp\build\bin\Release\whisper-server.exe buzz\whisper_cpp\
copy /Y dll_backup\SDL2.dll buzz\whisper_cpp\
PowerShell -NoProfile -ExecutionPolicy Bypass -Command "if (-not (Test-Path 'buzz\whisper_cpp\ggml-silero-v6.2.0.bin')) { Start-BitsTransfer -Source https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin -Destination 'buzz\whisper_cpp\ggml-silero-v6.2.0.bin' }"

echo Running dll backup copy...
xcopy .\dll_backup\* .\buzz\ /E /H /C /I /Y

echo Building PyInstaller executable...
D:\Tools\uv.exe run pyinstaller --noconfirm Buzz.spec

echo Building installer...
"D:\Tools\InnoSetup\iscc.exe" installer.iss
