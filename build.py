import platform
import subprocess

if platform.system() == 'Darwin':
    libwhisper = 'libwhisper.dylib'
elif platform.system() == 'Windows':
    libwhisper = 'whisper.dll'
elif platform.system() == 'Linux':
    libwhisper = 'libwhisper.so'


def build(setup_kwargs):
    subprocess.call(['make', 'whisper_cpp'])
    subprocess.call(['ctypesgen', './whisper.cpp/whisper.h', f'-l{libwhisper}', '-o', 'buzz/whisper_cpp.py'])
    raise Exception('Failed')
    print('Written buzz/whisper_cpp.py')


if __name__ == "__main__":
    build({})
