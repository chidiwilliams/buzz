import logging
import os
import warnings
import wave
from datetime import datetime

import pyaudio
import whisper

logging.basicConfig(level=logging.DEBUG)
warnings.filterwarnings('ignore')

model = whisper.load_model("tiny")

frames_per_buffer = 1024
sample_format = pyaudio.paInt16
channels = 1
rate = 44100
clip_duration = 4
model_seconds = 5
overlap = 0

p = pyaudio.PyAudio()

logging.debug("Recording...")

frames = []


def stream_callback(in_data, frame_count, time_info, status):
    frames.append(in_data)
    return in_data, pyaudio.paContinue


stream = p.open(format=sample_format,
                channels=channels,
                rate=rate,
                frames_per_buffer=frames_per_buffer,
                input=True,
                stream_callback=stream_callback)

stream.start_stream()

fps = int(rate / frames_per_buffer * clip_duration)

while True:
    if len(frames) > fps:
        fname = ''.join(
            ['.', '/clip-', datetime.utcnow().strftime('%Y%m%d%H%M%S'), '.wav'])
        try:
            clip = []
            for i in range(0, fps):
                clip.append(frames[i])

            wavefile = wave.open(fname, 'wb')
            wavefile.setnchannels(channels)
            wavefile.setsampwidth(p.get_sample_size(pyaudio.paInt16))
            wavefile.setframerate(rate)
            wavefile.writeframes(b''.join(clip))
            wavefile.close()

            result = model.transcribe(audio=fname, language="en")
            print(result["text"])

            frames = frames[fps:]
            logging.debug("Buffer size: ", len(frames))
        except KeyboardInterrupt as e:
            logging.debug("Ending recording...")
            stream.stop_stream()
            stream.close()
            p.terminate()
        finally:
            os.remove(fname)
