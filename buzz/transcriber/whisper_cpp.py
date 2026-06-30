import platform
import os
import re
import sys
import logging
import subprocess
import json
from typing import List, Optional
from buzz.assets import APP_BASE_DIR
from buzz.transcriber.transcriber import Segment, Task, FileTranscriptionTask
from buzz.transcriber.file_transcriber import app_env


IS_VULKAN_SUPPORTED = False
try:
    import vulkan

    instance = vulkan.vkCreateInstance(vulkan.VkInstanceCreateInfo(), None)
    vulkan.vkDestroyInstance(instance, None)
    vulkan_version = vulkan.vkEnumerateInstanceVersion()
    major = (vulkan_version >> 22) & 0x3FF
    minor = (vulkan_version >> 12) & 0x3FF

    logging.debug("Vulkan version = %s.%s", major, minor)

    # On macOS, default whisper_cpp is compiled with CoreML (Apple Silicon) or Vulkan (Intel).
    if platform.system() in ("Linux", "Windows") and ((major > 1) or (major == 1 and minor >= 2)):
        IS_VULKAN_SUPPORTED = True

except (ImportError, Exception) as e:
    logging.debug(f"Vulkan import error: {e}")

    IS_VULKAN_SUPPORTED = False


def get_whisper_cli_path() -> str:
    """Return the path to the bundled whisper-cli executable."""
    cli_executable = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"
    whisper_cli_path = os.path.join(APP_BASE_DIR, "whisper_cpp", cli_executable)

    # If running Mac and Windows installed version
    if not os.path.exists(whisper_cli_path):
        whisper_cli_path = os.path.join(APP_BASE_DIR, "buzz", "whisper_cpp", cli_executable)

    return whisper_cli_path


def _make_offset_mapper(segment_data, vad_enabled):
    """Return a function mapping a token offset to original audio time."""
    if not vad_enabled:
        return lambda offset: offset

    token_offsets = [
        (
            int(t.get("offsets", {}).get("from", 0)),
            int(t.get("offsets", {}).get("to", 0)),
        )
        for t in segment_data.get("tokens", [])
        if not t.get("text", "").startswith("[_")
    ]
    if not token_offsets:
        return lambda offset: offset

    vad_min = min(start for start, _ in token_offsets)
    vad_max = max(end for _, end in token_offsets)
    orig_from = int(segment_data.get("offsets", {}).get("from", 0))
    orig_to = int(segment_data.get("offsets", {}).get("to", 0))

    span = vad_max - vad_min
    if span <= 0:
        return lambda offset: orig_from

    scale = (orig_to - orig_from) / span
    return lambda offset: int(orig_from + (offset - vad_min) * scale)


def _flush_complete_chars(buffer: bytes, start: int, end: int, segments: list) -> bytes:
    """Extract and output all complete UTF-8 characters from buffer.
    Returns any remaining incomplete bytes."""
    remaining = buffer
    pos = 0

    while pos < len(remaining):
        for char_len in range(1, min(5, len(remaining) - pos + 1)):
            try:
                char = remaining[pos:pos + char_len].decode("utf-8")
                if char.strip():
                    segments.append(
                        Segment(
                            start=start,
                            end=end,
                            text=char,
                            translation=""
                        )
                    )
                pos += char_len
                break
            except UnicodeDecodeError:
                if char_len == 4 or pos + char_len >= len(remaining):
                    return remaining[pos:]
        else:
            return remaining[pos:]

    return b""


def _append_word(buffer: bytes, start: int, end: int, segments: list) -> bool:
    """Try to decode and append a word segment, handling multi-byte UTF-8"""
    if not buffer:
        return True

    try:
        text = buffer.decode("utf-8").strip()
        if text:
            segments.append(
                Segment(
                    start=start,
                    end=end,
                    text=text,
                    translation=""
                )
            )
        return True
    except UnicodeDecodeError:
        return False


class WhisperCpp:
    @staticmethod
    def _convert_to_wav(file_path: str) -> str:
        """Convert audio file to WAV format using ffmpeg."""
        temp_file = file_path + ".wav"
        logging.info(f"Converting {file_path} to WAV format")

        ffmpeg_cmd = [
            "ffmpeg",
            "-i", file_path,
            "-ar", "16000",
            "-ac", "1",
            "-y",
            temp_file
        ]

        try:
            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    startupinfo=si,
                    env=app_env,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=True
                )
            else:
                subprocess.run(ffmpeg_cmd, capture_output=True, check=True)

            return temp_file
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to convert audio file: {e.stderr.decode()}")
        except FileNotFoundError:
            raise Exception("ffmpeg not found. Please install ffmpeg to process this audio format.")

    @staticmethod
    def _build_command(task, file_to_process, language, vad_enabled) -> list:
        """Build the whisper-cli command line."""
        cmd = [
            get_whisper_cli_path(),
            "--model", task.model_path,
            "--language", language,
            "--print-progress",
            "--suppress-nst",
            "--max-context", "0",
            "--entropy-thold", "2.8",
            "--output-json-full",
            "--threads", str(os.getenv("BUZZ_WHISPERCPP_N_THREADS", (os.cpu_count() or 8) // 2)),
            "-f", file_to_process,
        ]

        if vad_enabled:
            vad_model_path = os.path.join(
                os.path.dirname(get_whisper_cli_path()), "ggml-silero-v6.2.0.bin"
            )
            cmd.extend(["--vad", "--vad-model", vad_model_path])

        if task.transcription_options.task == Task.TRANSLATE:
            cmd.extend(["--translate"])

        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        if force_cpu != "false" or (not IS_VULKAN_SUPPORTED and platform.system() != "Darwin"):
            cmd.extend(["--no-gpu"])

        print(f"Running Whisper CLI: {' '.join(cmd)}")
        return cmd

    @staticmethod
    def _run_whisper(cmd) -> int:
        """Run whisper-cli subprocess and return the return code."""
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=si,
                env=app_env,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        for line in iter(process.stderr.readline, ''):
            sys.stderr.write(line)

        process.wait()
        return process.returncode

    @staticmethod
    def _read_json_output(file_to_process: str) -> dict:
        """Read the JSON output file generated by whisper-cli."""
        json_output_path = f"{file_to_process}.json"
        with open(json_output_path, 'r', encoding='latin-1') as f:
            return json.load(f)

    @staticmethod
    def _parse_word_level_timings(result, language, vad_enabled) -> list:
        """Parse word-level timings from whisper-cli JSON output."""
        segments = []
        transcription = result.get("transcription", [])
        non_space_languages = {"zh", "ja", "th", "lo", "km", "my"}
        is_non_space_language = language in non_space_languages

        for segment_data in transcription:
            tokens = segment_data.get("tokens", [])
            map_offset = _make_offset_mapper(segment_data, vad_enabled)

            if is_non_space_language:
                char_buffer = b""
                char_start = 0
                char_end = 0

                for token_data in tokens:
                    token_text = token_data.get("text", "")

                    if token_text.startswith("[_") or not token_text:
                        continue

                    token_start = map_offset(int(token_data.get("offsets", {}).get("from", 0)))
                    token_end = map_offset(int(token_data.get("offsets", {}).get("to", 0)))

                    token_bytes = token_text.encode("latin-1")

                    if not char_buffer:
                        char_start = token_start

                    char_buffer += token_bytes
                    char_end = token_end

                    char_buffer = _flush_complete_chars(char_buffer, char_start, char_end, segments)

                    if not char_buffer:
                        char_start = token_end

                if char_buffer:
                    _flush_complete_chars(char_buffer, char_start, char_end, segments)
            else:
                word_buffer = b""
                word_start = 0
                word_end = 0

                for token_data in tokens:
                    token_text = token_data.get("text", "")

                    if token_text.startswith("[_") or not token_text:
                        continue

                    token_p = token_data.get("p", 1.0)
                    if token_p < 0.01:
                        continue

                    token_start = map_offset(int(token_data.get("offsets", {}).get("from", 0)))
                    token_end = map_offset(int(token_data.get("offsets", {}).get("to", 0)))

                    token_bytes = token_text.encode("latin-1")

                    if token_bytes.startswith(b" ") and word_buffer:
                        _append_word(word_buffer, word_start, word_end, segments)
                        word_buffer = token_bytes
                        word_start = token_start
                        word_end = token_end
                    elif token_bytes.startswith(b", "):
                        word_buffer += b","
                        _append_word(word_buffer, word_start, word_end, segments)
                        word_buffer = token_bytes.lstrip(b",")
                        word_start = token_start
                        word_end = token_end
                    else:
                        if not word_buffer:
                            word_start = token_start
                        word_buffer += token_bytes
                        word_end = token_end

                _append_word(word_buffer, word_start, word_end, segments)

        return segments

    @staticmethod
    def _parse_segment_timings(result) -> list:
        """Parse segment-level timings from whisper-cli JSON output."""
        segments = []
        transcription = result.get("transcription", [])
        for segment_data in transcription:
            segment_text_latin1 = segment_data.get("text", "")
            try:
                segment_text = segment_text_latin1.encode("latin-1").decode("utf-8").strip()
            except (UnicodeDecodeError, UnicodeEncodeError):
                segment_text = segment_text_latin1.strip()

            segments.append(
                Segment(
                    start=int(segment_data.get("offsets", {}).get("from", 0)),
                    end=int(segment_data.get("offsets", {}).get("to", 0)),
                    text=segment_text,
                    translation=""
                )
            )
        return segments

    @staticmethod
    def _cleanup_files(temp_file, json_output_path):
        """Clean up temporary files."""
        if json_output_path and os.path.exists(json_output_path):
            try:
                os.remove(json_output_path)
            except Exception as e:
                print(f"Failed to remove JSON output file {json_output_path}: {e}")

        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as e:
                print(f"Failed to remove temporary file {temp_file}: {e}")

    @staticmethod
    def transcribe(task: FileTranscriptionTask) -> List[Segment]:
        """Transcribe audio using whisper-cli subprocess."""
        language = (
            task.transcription_options.language
            if task.transcription_options.language is not None
            else "auto"
        )

        supported_formats = ('.mp3', '.wav', '.flac')
        file_ext = os.path.splitext(task.file_path)[1].lower()

        temp_file = None
        file_to_process = task.file_path

        if file_ext not in supported_formats:
            temp_file = WhisperCpp._convert_to_wav(task.file_path)
            file_to_process = temp_file

        vad_model_path = os.path.join(
            os.path.dirname(get_whisper_cli_path()), "ggml-silero-v6.2.0.bin"
        )
        vad_enabled = os.path.exists(vad_model_path)

        cmd = WhisperCpp._build_command(task, file_to_process, language, vad_enabled)
        return_code = WhisperCpp._run_whisper(cmd)

        if return_code != 0:
            WhisperCpp._cleanup_files(temp_file, None)
            raise Exception(f"whisper-cli failed with return code {return_code}")

        try:
            result = WhisperCpp._read_json_output(file_to_process)
            if task.transcription_options.word_level_timings:
                segments = WhisperCpp._parse_word_level_timings(
                    result, language, vad_enabled
                )
            else:
                segments = WhisperCpp._parse_segment_timings(result)
            return segments
        finally:
            json_output_path = f"{file_to_process}.json"
            WhisperCpp._cleanup_files(temp_file, json_output_path)

    @staticmethod
    def detect_language(file_path: str, model_path: str) -> Optional[str]:
        """Detect the spoken language of an audio file using whisper-cli.

        Runs whisper-cli with ``--detect-language`` which exits right after
        detecting the language (much faster than a full transcription). Returns
        the detected language code (e.g. ``"en"``) or ``None`` if detection
        failed.
        """
        whisper_cli_path = get_whisper_cli_path()

        # whisper-cli reads flac, mp3, ogg and wav directly. Convert anything
        # else to WAV first, mirroring transcribe().
        supported_formats = ('.mp3', '.wav', '.flac', '.ogg')
        file_ext = os.path.splitext(file_path)[1].lower()

        temp_file = None
        file_to_process = file_path

        if file_ext not in supported_formats:
            temp_file = file_path + ".wav"
            logging.info(f"Converting {file_path} to WAV format for language detection")

            ffmpeg_cmd = [
                "ffmpeg",
                "-i", file_path,
                "-ar", "16000",
                "-ac", "1",
                "-y",
                temp_file,
            ]

            try:
                if sys.platform == "win32":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = subprocess.SW_HIDE
                    subprocess.run(
                        ffmpeg_cmd,
                        capture_output=True,
                        startupinfo=si,
                        env=app_env,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        check=True,
                    )
                else:
                    subprocess.run(ffmpeg_cmd, capture_output=True, check=True)

                file_to_process = temp_file
            except subprocess.CalledProcessError as e:
                raise Exception(f"Failed to convert audio file: {e.stderr.decode()}")
            except FileNotFoundError:
                raise Exception("ffmpeg not found. Please install ffmpeg to process this audio format.")

        cmd = [
            whisper_cli_path,
            "--model", model_path,
            "--detect-language",
            "-f", file_to_process,
        ]

        # Force CPU if specified (mirrors transcribe()).
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        if force_cpu != "false" or (not IS_VULKAN_SUPPORTED and platform.system() != "Darwin"):
            cmd.extend(["--no-gpu"])

        print(f"Running Whisper CLI language detection: {' '.join(cmd)}")

        try:
            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    startupinfo=si,
                    env=app_env,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

            # whisper-cli writes the detection line to stderr, e.g.:
            #   whisper_full_with_state: auto-detected language: fr (p = 0.99)
            output = (result.stderr or "") + (result.stdout or "")
            match = re.search(r"auto-detected language:\s*([a-zA-Z]{2,3})", output)
            if match:
                return match.group(1).lower()

            logging.warning("Language detection produced no result")
            return None
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"Failed to remove temporary file {temp_file}: {e}")