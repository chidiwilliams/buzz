import os.path

test_audio_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../testdata/whisper-french.mp3")
)

test_multibyte_utf8_audio_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../testdata/whisper-latvian.wav")
)