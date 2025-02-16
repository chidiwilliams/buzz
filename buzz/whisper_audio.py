import subprocess
import numpy as np
import sys
import logging

SAMPLE_RATE = 16000

N_FFT = 400
HOP_LENGTH = 160
CHUNK_LENGTH = 30
N_SAMPLES = CHUNK_LENGTH * SAMPLE_RATE  # 480000 samples in a 30-second chunk


def load_audio(file: str, sr: int = SAMPLE_RATE):
    """
    Open an audio file and read as mono waveform, resampling as necessary

    Parameters
    ----------
    file: str
        The audio file to open

    sr: int
        The sample rate to resample the audio if necessary

    Returns
    -------
    A NumPy array containing the audio waveform, in float32 dtype.
    """

    # This launches a subprocess to decode audio while down-mixing
    # and resampling as necessary.  Requires the ffmpeg CLI in PATH.
    # fmt: off
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-threads", "0",
        "-i", file,
        "-f", "s16le",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-ar", str(sr),
        "-loglevel", "panic",
        "-"
    ]
    # fmt: on
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(cmd, capture_output=True, startupinfo=si)
    else:
        result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        logging.warning(f"FFMPEG audio load warning. Process return code was not zero: {result.returncode}")

    if len(result.stderr):
        logging.warning(f"FFMPEG audio load error. Error: {result.stderr.decode()}")
        raise RuntimeError(f"FFMPEG Failed to load audio: {result.stderr.decode()}")

    return np.frombuffer(result.stdout, np.int16).flatten().astype(np.float32) / 32768.0
