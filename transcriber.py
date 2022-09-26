import logging
import os
import sys
import tempfile
import wave
from datetime import datetime
from typing import Callable, Optional

import pyaudio
import whisper

# When the app is opened as a .app from Finder, the path doesn't contain /usr/local/bin
# which breaks the call to run `ffmpeg`. This sets the path manually to fix that.
os.environ["PATH"] += os.pathsep + "/usr/local/bin"


class Transcriber:
    """Transcriber records audio from a system microphone and transcribes it into text using Whisper."""

    # Number of times the queue is greater than the frames_per_chunk
    # after which the transcriber will stop queueing new frames
    chunk_drop_factor = 5

    def __init__(self, model_name: str, language: Optional[str], text_callback: Callable[[str], None]) -> None:
        self.pyaudio = pyaudio.PyAudio()
        self.model_name = model_name
        self.model = whisper.load_model(model_name)
        self.stream = None
        self.frames = []
        self.text_callback = text_callback
        self.stopped = False
        self.language = language

    def start_recording(self, frames_per_buffer=1024, sample_format=pyaudio.paInt16,
                        channels=1, rate=44100, chunk_duration=5, input_device_index: Optional[int] = None):
        logging.debug("Recording with language \"%s\", model \"%s\"" %
                      (self.language, self.model_name))
        self.stream = self.pyaudio.open(format=sample_format,
                                        channels=channels,
                                        rate=rate,
                                        frames_per_buffer=frames_per_buffer,
                                        input=True,
                                        input_device_index=input_device_index,
                                        stream_callback=self.stream_callback)

        self.stream.start_stream()

        self.frames_per_chunk = int(rate / frames_per_buffer * chunk_duration)
        while True:
            if self.stopped:
                self.frames = []
                logging.debug("Recording stopped. Exiting...")
                return
            if len(self.frames) > self.frames_per_chunk:
                logging.debug("Buffer size: %d. Transcribing next %d frames..." %
                              (len(self.frames), self.frames_per_chunk))
                chunk_path = self.chunk_path()
                try:
                    clip = []
                    # TODO: Breaking the audio into chunks might make it more difficult for
                    # Whisper to work. Could it be helpful to re-use a section of the previous
                    # chunk in the next iteration?
                    for i in range(0, self.frames_per_chunk):
                        clip.append(self.frames[i])
                    frames = b''.join(clip)

                    # TODO: Can the chunk be passed to whisper in-memory instead?
                    self.write_chunk(chunk_path, channels, rate, frames)

                    result = self.model.transcribe(
                        audio=chunk_path, language=self.language)

                    logging.debug("Received next result: \"%s\"" %
                                  result["text"])
                    self.text_callback(result["text"])

                    os.remove(chunk_path)

                    # TODO: Implement dropping frames if the queue gets too large
                    self.frames = self.frames[self.frames_per_chunk:]
                except KeyboardInterrupt as e:
                    self.stop_recording()
                    os.remove(chunk_path)
                    sys.exit(0)

    def stream_callback(self, in_data, frame_count, time_info, status):
        # Append new frame only if the queue is not larger than the chunk drop factor
        if (len(self.frames) / self.frames_per_chunk) < self.chunk_drop_factor:
            self.frames.append(in_data)
        return in_data, pyaudio.paContinue

    def stop_recording(self):
        if self.stream != None:
            logging.debug("Ending recording...")
            self.stopped = True
            self.stream.stop_stream()
            self.stream.close()
            self.pyaudio.terminate()

    def write_chunk(self, path, channels, rate, frames):
        logging.debug('Writing chunk to path: %s' % path)
        wavefile = wave.open(path, 'wb')
        wavefile.setnchannels(channels)
        wavefile.setsampwidth(
            self.pyaudio.get_sample_size(pyaudio.paInt16))
        wavefile.setframerate(rate)
        wavefile.writeframes(frames)
        wavefile.close()
        return path

    def chunk_path(self) -> str:
        """Returns the path where a chunk should be saved using the
        system's temp directory and a unique filename.
        """
        chunk_id = "clip-%s.wav" % (datetime.utcnow().strftime('%Y%m%d%H%M%S'))
        return os.path.join(tempfile.gettempdir(), chunk_id)
