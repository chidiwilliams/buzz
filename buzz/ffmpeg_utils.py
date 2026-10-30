import os
import shutil
import sys

from buzz.assets import APP_BASE_DIR


def _find_binary(name: str) -> str:
    """Locate an ffmpeg binary, preferring one bundled with a frozen build."""
    path = shutil.which(name)
    if path:
        return path

    search_dirs = [
        getattr(sys, "_MEIPASS", ""),
        APP_BASE_DIR,
        os.path.join(APP_BASE_DIR, "_internal"),
    ]
    for directory in search_dirs:
        if not directory:
            continue
        for candidate in (name, name + ".exe"):
            bundled = os.path.join(directory, candidate)
            if os.path.exists(bundled):
                return bundled

    return name


def find_ffmpeg() -> str:
    return _find_binary("ffmpeg")


def find_ffprobe() -> str:
    return _find_binary("ffprobe")


def audio_stream_duration(info: dict) -> float:
    """
    Duration in seconds of the first audio stream in ffprobe's JSON output
    of streams and format, or 0 if unknown. The buffer for decoded samples is
    sized by it, so it must be the audio's: a video's can be far longer than
    its audio track.
    """
    streams = info.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        return 0
    # Matroska stores no duration for a stream, but its muxers write the
    # measured one as a tag. Read that first, as an ffprobe may fill in the
    # stream's duration with the container's, i.e. the video's.
    tag = (audio.get("tags") or {}).get("DURATION")
    if tag:
        # Other muxers and tag editors may write it in another format, e.g.
        # "N/A", in which case the stream's or container's duration is used
        try:
            hours, minutes, seconds = tag.split(":")
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        except ValueError:
            pass
    if audio.get("duration"):
        return float(audio["duration"])
    # The container's duration is the audio's only when it holds nothing else
    if all(s.get("codec_type") == "audio" for s in streams):
        return float(info.get("format", {}).get("duration") or 0)
    return 0
