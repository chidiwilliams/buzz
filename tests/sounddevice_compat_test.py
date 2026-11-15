import importlib
import sys

import pytest

import buzz.sounddevice_compat


@pytest.fixture
def unavailable_compat(monkeypatch):
    # A None entry makes `import sounddevice` raise, like PortAudio failing to initialize.
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    compat = importlib.reload(buzz.sounddevice_compat)
    yield compat
    monkeypatch.undo()
    importlib.reload(buzz.sounddevice_compat)


def test_real_sounddevice_when_available():
    import sounddevice

    assert buzz.sounddevice_compat.is_audio_available()
    assert buzz.sounddevice_compat.sounddevice is sounddevice
    assert buzz.sounddevice_compat.PortAudioError is sounddevice.PortAudioError


def test_unavailable_lists_no_devices(unavailable_compat):
    sd = unavailable_compat.sounddevice

    assert not unavailable_compat.is_audio_available()
    assert unavailable_compat.AUDIO_UNAVAILABLE_REASON
    assert list(sd.query_devices()) == []
    assert sd.query_hostapis() == ()
    assert sd.default.device == (-1, -1)


def test_unavailable_streams_raise_port_audio_error(unavailable_compat):
    sd = unavailable_compat.sounddevice

    with pytest.raises(unavailable_compat.PortAudioError, match="Audio devices are unavailable"):
        sd.InputStream(samplerate=16000, channels=1)
    with pytest.raises(unavailable_compat.PortAudioError):
        sd.OutputStream(samplerate=16000, channels=1)
    with pytest.raises(unavailable_compat.PortAudioError):
        sd.check_input_settings(device=None, samplerate=16000)
    with pytest.raises(unavailable_compat.PortAudioError):
        sd.query_devices(device=0)


def test_unavailable_refresh_is_harmless(unavailable_compat):
    sd = unavailable_compat.sounddevice
    sd._terminate()
    sd._initialize()


def test_audio_file_player_not_ready_when_unavailable(monkeypatch):
    import buzz.sounddevice_player as player_module

    monkeypatch.setattr(player_module, "is_audio_available", lambda: False)
    player = player_module.AudioFilePlayer("testdata/whisper-french.mp3")

    assert not player.ready
    assert player.samples is None
