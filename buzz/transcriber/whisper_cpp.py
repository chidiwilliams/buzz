import platform
import os
import sys
import logging
import subprocess
import json
from typing import List
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


class WhisperCpp:
    @staticmethod
    def transcribe(task: FileTranscriptionTask) -> List[Segment]:
        """Transcribe audio using whisper-cli subprocess."""
        cli_executable = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"
        whisper_cli_path = os.path.join(APP_BASE_DIR, "whisper_cpp", cli_executable)

        # If running Mac and Windows installed version
        if not os.path.exists(whisper_cli_path):
            whisper_cli_path = os.path.join(APP_BASE_DIR, "buzz", "whisper_cpp", cli_executable)

        language = (
            task.transcription_options.language
            if task.transcription_options.language is not None
            else "en"
        )

        # Check if file format is supported, convert to WAV if not
        supported_formats = ('.mp3', '.wav', '.flac')
        file_ext = os.path.splitext(task.file_path)[1].lower()

        temp_file = None
        file_to_process = task.file_path

        if file_ext not in supported_formats:
            temp_file = task.file_path + ".wav"

            logging.info(f"Converting {task.file_path} to WAV format")

            # Convert using ffmpeg
            ffmpeg_cmd = [
                "ffmpeg",
                "-i", task.file_path,
                "-ar", "16000",  # 16kHz sample rate (whisper standard)
                "-ac", "1",      # mono
                "-y",            # overwrite output file
                temp_file
            ]

            try:
                if sys.platform == "win32":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = subprocess.SW_HIDE
                    result = subprocess.run(
                        ffmpeg_cmd,
                        capture_output=True,
                        startupinfo=si,
                        env=app_env,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        check = True
                    )
                else:
                    result = subprocess.run(ffmpeg_cmd, capture_output=True, check=True)

                file_to_process = temp_file
            except subprocess.CalledProcessError as e:
                raise Exception(f"Failed to convert audio file: {e.stderr.decode()}")
            except FileNotFoundError:
                raise Exception("ffmpeg not found. Please install ffmpeg to process this audio format.")
    
        # Build the command
        cmd = [
            whisper_cli_path,
            "--model", task.model_path,
            "--language", language,
            "--print-progress",
            "--suppress-nst",
            # Protections against hallucinated repetition. Seems to be problem on macOS
            # https://github.com/ggml-org/whisper.cpp/issues/1507
            "--max-context", "64",
            "--entropy-thold", "2.8",
            "--output-json-full",
            "--threads", str(os.getenv("BUZZ_WHISPERCPP_N_THREADS", (os.cpu_count() or 8) // 2)),
            "-f", file_to_process,
        ]
    
        # Add translate flag if needed
        if task.transcription_options.task == Task.TRANSLATE:
            cmd.extend(["--translate"])
    
        # Force CPU if specified
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        if force_cpu != "false" or (not IS_VULKAN_SUPPORTED and platform.system() != "Darwin"):
            cmd.extend(["--no-gpu"])

        print(f"Running Whisper CLI: {' '.join(cmd)}")

        # Run the whisper-cli process
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
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
            )
    
        # Capture stderr for progress updates
        stderr_output = []
        while True:
            line = process.stderr.readline()
            if not line:
                break
            stderr_output.append(line.strip())
            # Progress is written to stderr
            sys.stderr.write(line)
    
        process.wait()
    
        if process.returncode != 0:
            # Clean up temp file if conversion was done
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"Failed to remove temporary file {temp_file}: {e}")
            raise Exception(f"whisper-cli failed with return code {process.returncode}")

        # Find and read the generated JSON file
        # whisper-cli generates: input_file.ext.json (e.g., file.mp3.json)
        json_output_path = f"{file_to_process}.json"
    
        try:
            # Read JSON with latin-1 to preserve raw bytes, then handle encoding per field
            # This is needed because whisper-cli can write invalid UTF-8 sequences for multi-byte characters
            with open(json_output_path, 'r', encoding='latin-1') as f:
                result = json.load(f)
    
            segments = []
    
            # Handle word-level timings
            if task.transcription_options.word_level_timings:
                # Extract word-level timestamps from tokens array
                # Combine tokens into words using similar logic as whisper_cpp.py
                transcription = result.get("transcription", [])
                for segment_data in transcription:
                    tokens = segment_data.get("tokens", [])
    
                    # Accumulate tokens into words
                    word_buffer = b""
                    word_start = 0
                    word_end = 0
    
                    def append_word(buffer: bytes, start: int, end: int):
                        """Try to decode and append a word segment, handling multi-byte UTF-8"""
                        if not buffer:
                            return True
    
                        # Try to decode as UTF-8
                        # https://github.com/ggerganov/whisper.cpp/issues/1798
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
                            # Multi-byte character is split, continue accumulating
                            return False
    
                    for token_data in tokens:
                        # Token text is read as latin-1, need to convert to bytes to get original data
                        token_text = token_data.get("text", "")
    
                        # Skip special tokens like [_TT_], [_BEG_]
                        if token_text.startswith("[_"):
                            continue
    
                        if not token_text:
                            continue
    
                        token_start = int(token_data.get("offsets", {}).get("from", 0))
                        token_end = int(token_data.get("offsets", {}).get("to", 0))
    
                        # Convert latin-1 string back to original bytes
                        # (latin-1 preserves byte values as code points)
                        token_bytes = token_text.encode("latin-1")
    
                        # Check if token starts with space - indicates new word
                        if token_bytes.startswith(b" ") and word_buffer:
                            # Save previous word
                            append_word(word_buffer, word_start, word_end)
                            # Start new word
                            word_buffer = token_bytes
                            word_start = token_start
                            word_end = token_end
                        elif token_bytes.startswith(b", "):
                            # Handle comma - save word with comma, then start new word
                            word_buffer += b","
                            append_word(word_buffer, word_start, word_end)
                            word_buffer = token_bytes.lstrip(b",")
                            word_start = token_start
                            word_end = token_end
                        else:
                            # Accumulate token into current word
                            if not word_buffer:
                                word_start = token_start
                            word_buffer += token_bytes
                            word_end = token_end
    
                    # Add the last word
                    append_word(word_buffer, word_start, word_end)
            else:
                # Use segment-level timestamps
                transcription = result.get("transcription", [])
                for segment_data in transcription:
                    # Segment text is also read as latin-1, convert back to UTF-8
                    segment_text_latin1 = segment_data.get("text", "")
                    try:
                        # Convert latin-1 string to bytes, then decode as UTF-8
                        segment_text = segment_text_latin1.encode("latin-1").decode("utf-8").strip()
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        # If conversion fails, use the original text
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
        finally:
            # Clean up the generated JSON file
            if os.path.exists(json_output_path):
                try:
                    os.remove(json_output_path)
                except Exception as e:
                    print(f"Failed to remove JSON output file {json_output_path}: {e}")

            # Clean up temporary audio file if conversion was done
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception as e:
                    print(f"Failed to remove temporary file {temp_file}: {e}")