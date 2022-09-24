import logging
import os
import wave
from datetime import datetime

import pyaudio
import whisper


class Transcriber:
    def __init__(self, model_name="tiny") -> None:
        self.pyaudio = pyaudio.PyAudio()
        self.model = whisper.load_model(model_name)
        self.stream = None
        self.frames = []

    def start_recording(self, frames_per_buffer=1024, sample_format=pyaudio.paInt16, channels=1, rate=44100, chunk_duration=4):
        logging.debug("Recording...")
        self.stream = self.pyaudio.open(format=sample_format,
                                        channels=channels,
                                        rate=rate,
                                        frames_per_buffer=frames_per_buffer,
                                        input=True,
                                        stream_callback=self.stream_callback)

        self.stream.start_stream()

        frames_per_chunk = int(rate / frames_per_buffer * chunk_duration)

        while True:
            if len(self.frames) > frames_per_chunk:
                chunk_path = self.chunk_path()
                try:
                    clip = []
                    for i in range(0, frames_per_chunk):
                        clip.append(self.frames[i])
                    frames = b''.join(clip)

                    self.write_chunk(chunk_path, channels, rate, frames)

                    result = self.model.transcribe(
                        audio=chunk_path, language="en")

                    print(result["text"])

                    os.remove(chunk_path)

                    self.frames = self.frames[frames_per_chunk:]
                    logging.debug("Buffer size: ", len(self.frames))
                except KeyboardInterrupt as e:
                    self.stop_recording()
                    os.remove(chunk_path)
                    raise e

    def stream_callback(self, in_data, frame_count, time_info, status):
        self.frames.append(in_data)
        return in_data, pyaudio.paContinue

    def stop_recording(self):
        logging.debug("Ending recording...")
        self.stream.stop_stream()
        self.stream.close()
        self.pyaudio.terminate()

    def write_chunk(self, path, channels, rate, frames):
        wavefile = wave.open(path, 'wb')
        wavefile.setnchannels(channels)
        wavefile.setsampwidth(
            self.pyaudio.get_sample_size(pyaudio.paInt16))
        wavefile.setframerate(rate)
        wavefile.writeframes(frames)
        wavefile.close()
        return path

    def chunk_path(self):
        base_dir = os.path.dirname(__file__)
        chunk_id = "clip-%s.wav" % (datetime.utcnow().strftime('%Y%m%d%H%M%S'))
        return os.path.join(base_dir, chunk_id)
