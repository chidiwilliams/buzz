import sys
from subprocess import Popen

import ffmpeg
import whisper

INPUT_FILE = 'testdata/whisper-french.mp3'
OUTPUT_FILE = 'testdata/whisper-french.wav'


def reader(pipe, queue):
    try:
        with pipe:
            for line in iter(pipe.readline, b''):
                queue.put((pipe, line))
    finally:
        queue.put(None)


ffmpeg.input(INPUT_FILE).output(
    OUTPUT_FILE,
    acodec="pcm_s16le",
    ac=1, ar=whisper.audio.SAMPLE_RATE,
).overwrite_output().run()

process = Popen([
    'whisper_cpp',
    '-f', OUTPUT_FILE,
    '-m', '/Users/chidiwilliams/Library/Caches/Buzz/ggml-model-whisper-tiny.bin'],
    stdout=sys.stdout,
    stderr=sys.stderr, bufsize=1)

process.wait()
