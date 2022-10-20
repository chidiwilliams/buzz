
import hashlib
import os
import warnings
from typing import Callable, Tuple, Union

import numpy as np
import requests
import torch
import whisper
from appdirs import user_cache_dir
from whisper import Whisper
from whisper.audio import *
from whisper.decoding import *
from whisper.tokenizer import *
from whisper.utils import *

from transcriber import WhisperCppModel


class Stopped(Exception):
    pass


class ModelLoader:
    stopped = False

    def __init__(self, name: str, use_whisper_cpp=False,
                 on_download_model_chunk: Callable[[int, int], None] = lambda *_: None) -> None:
        self.name = name
        self.on_download_model_chunk = on_download_model_chunk
        self.use_whisper_cpp = use_whisper_cpp

    def load(self) -> Union[Whisper, WhisperCppModel]:
        if self.use_whisper_cpp:
            base_dir = user_cache_dir('Buzz')
            model_path = os.path.join(
                base_dir, f'ggml-model-whisper-{self.name}.bin')

            if os.path.exists(model_path) and not os.path.isfile(model_path):
                raise RuntimeError(
                    f"{model_path} exists and is not a regular file")

            # todo: implement sha256 hash checking

            if os.path.isfile(model_path):
                return WhisperCppModel(model_path)

            raise RuntimeError('unimplemented: download ggml model')
        return load_model(
            name=self.name, is_stopped=self.is_stopped,
            on_download_model_chunk=self.on_download_model_chunk)

    def stop(self):
        self.stopped = True

    def is_stopped(self):
        return self.stopped


def load_model(
        name: str, is_stopped: Callable[[], bool],
        on_download_model_chunk: Callable[[int, int], None] = lambda *_: None):
    """
    Loads a Whisper ASR model with cancellation and progress reporting.

    This is a patch for whisper.load_model that downloads the models using the requests module
    instead of urllib.request to allow the program get the correct SSL certificates when run from
    a PyInstaller application.
    """
    download_root = os.path.join(
        os.path.expanduser("~"), ".cache", "whisper")

    url = whisper._MODELS[name]
    _download(
        url=url, root=download_root, in_memory=False,
        on_download_model_chunk=on_download_model_chunk,
        is_stopped=is_stopped)

    download_target = os.path.join(download_root, os.path.basename(url))

    return whisper.load_model(name=download_target, download_root=download_root)


DONWLOAD_CHUNK_SIZE = 8192


def _download(
        url: str, root: str, in_memory: bool,
        on_download_model_chunk: Callable[[int, int], None],
        is_stopped: Callable[[], bool]) -> Union[bytes, str]:
    """ See whisper._download """
    os.makedirs(root, exist_ok=True)

    expected_sha256 = url.split("/")[-2]
    download_target = os.path.join(root, os.path.basename(url))

    if os.path.exists(download_target) and not os.path.isfile(download_target):
        raise RuntimeError(
            f"{download_target} exists and is not a regular file")

    if os.path.isfile(download_target):
        model_bytes = open(download_target, "rb").read()
        if hashlib.sha256(model_bytes).hexdigest() == expected_sha256:
            return model_bytes if in_memory else download_target
        else:
            warnings.warn(
                f"{download_target} exists, but the SHA256 checksum does not match; re-downloading the file")

    with requests.get(url, stream=True) as source, open(download_target, 'wb') as output:
        source.raise_for_status()

        current_size = 0
        total_size = int(source.headers.get('Content-Length', 0))
        for chunk in source.iter_content(chunk_size=DONWLOAD_CHUNK_SIZE):
            if is_stopped():
                os.unlink(download_target)
                raise Stopped

            output.write(chunk)
            current_size += len(chunk)
            on_download_model_chunk(current_size, total_size)

    model_bytes = open(download_target, "rb").read()
    if hashlib.sha256(model_bytes).hexdigest() != expected_sha256:
        raise RuntimeError(
            "Model has been downloaded but the SHA256 checksum does not not match. Please retry loading the model.")

    return model_bytes if in_memory else download_target


def transcribe(
    model: "Whisper",
    audio: Union[str, np.ndarray, torch.Tensor],
    *,
    progress_callback: Callable[[int, int], None],
    check_stopped: Callable[[], bool],
    temperature: Union[float, Tuple[float, ...]] = (
        0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    compression_ratio_threshold: Optional[float] = 2.4,
    logprob_threshold: Optional[float] = -1.0,
    no_speech_threshold: Optional[float] = 0.6,
    condition_on_previous_text: bool = True,
    **decode_options,
):
    """Copy of whisper.transcribe that reports progress via progress_callback and can be stopped via check_stopped"""
    dtype = torch.float16 if decode_options.get(
        "fp16", True) else torch.float32
    if model.device == torch.device("cpu"):
        if torch.cuda.is_available():
            warnings.warn("Performing inference on CPU when CUDA is available")
        if dtype == torch.float16:
            warnings.warn("FP16 is not supported on CPU; using FP32 instead")
            dtype = torch.float32

    if dtype == torch.float32:
        decode_options["fp16"] = False

    mel = log_mel_spectrogram(audio)

    if decode_options.get("language", None) is None:
        if not model.is_multilingual:
            decode_options["language"] = "en"
        else:
            segment = pad_or_trim(mel, N_FRAMES).to(model.device).to(dtype)
            _, probs = model.detect_language(segment)
            decode_options["language"] = max(probs, key=probs.get)

    language = decode_options["language"]
    task = decode_options.get("task", "transcribe")
    tokenizer = get_tokenizer(model.is_multilingual,
                              language=language, task=task)

    def decode_with_fallback(segment: torch.Tensor) -> DecodingResult:
        temperatures = [temperature] if isinstance(
            temperature, (int, float)) else temperature
        decode_result = None

        for t in temperatures:
            kwargs = {**decode_options}
            if t > 0:
                # disable beam_size and patience when t > 0
                kwargs.pop("beam_size", None)
                kwargs.pop("patience", None)
            else:
                # disable best_of when t == 0
                kwargs.pop("best_of", None)

            options = DecodingOptions(**kwargs, temperature=t)
            decode_result = model.decode(segment, options)

            needs_fallback = False
            if compression_ratio_threshold is not None and decode_result.compression_ratio > compression_ratio_threshold:
                needs_fallback = True  # too repetitive
            if logprob_threshold is not None and decode_result.avg_logprob < logprob_threshold:
                needs_fallback = True  # average log probability is too low

            if not needs_fallback:
                break

        return decode_result

    seek = 0
    input_stride = exact_div(
        N_FRAMES, model.dims.n_audio_ctx
    )  # mel frames per output token: 2
    time_precision = (
        input_stride * HOP_LENGTH / SAMPLE_RATE
    )  # time per output token: 0.02 (seconds)
    all_tokens = []
    all_segments = []
    prompt_reset_since = 0

    initial_prompt = decode_options.pop("initial_prompt", None) or []
    if initial_prompt:
        initial_prompt = tokenizer.encode(" " + initial_prompt.strip())
        all_tokens.extend(initial_prompt)

    def add_segment(
        *, start: float, end: float, text_tokens: torch.Tensor, result: DecodingResult
    ):
        text = tokenizer.decode(
            [token for token in text_tokens if token < tokenizer.eot])
        if len(text.strip()) == 0:  # skip empty text output
            return

        all_segments.append(
            {
                "id": len(all_segments),
                "seek": seek,
                "start": start,
                "end": end,
                "text": text,
                "tokens": result.tokens,
                "temperature": result.temperature,
                "avg_logprob": result.avg_logprob,
                "compression_ratio": result.compression_ratio,
                "no_speech_prob": result.no_speech_prob,
            }
        )

    # show the progress bar when verbose is False (otherwise the transcribed text will be printed)
    num_frames = mel.shape[-1]
    previous_seek_value = seek

    progress_callback(0, num_frames)

    while seek < num_frames:
        if check_stopped():
            raise Stopped

        timestamp_offset = float(seek * HOP_LENGTH / SAMPLE_RATE)
        segment = pad_or_trim(mel[:, seek:], N_FRAMES).to(
            model.device).to(dtype)
        segment_duration = segment.shape[-1] * HOP_LENGTH / SAMPLE_RATE

        decode_options["prompt"] = all_tokens[prompt_reset_since:]
        result: DecodingResult = decode_with_fallback(segment)
        tokens = torch.tensor(result.tokens)

        if no_speech_threshold is not None:
            # no voice activity check
            should_skip = result.no_speech_prob > no_speech_threshold
            if logprob_threshold is not None and result.avg_logprob > logprob_threshold:
                # don't skip if the logprob is high enough, despite the no_speech_prob
                should_skip = False

            if should_skip:
                # fast-forward to the next segment boundary
                seek += segment.shape[-1]
                continue

        timestamp_tokens: torch.Tensor = tokens.ge(
            tokenizer.timestamp_begin)
        consecutive = torch.where(
            timestamp_tokens[:-1] & timestamp_tokens[1:])[0].add_(1)
        if len(consecutive) > 0:  # if the output contains two consecutive timestamp tokens
            last_slice = 0
            for current_slice in consecutive:
                sliced_tokens = tokens[last_slice:current_slice]
                start_timestamp_position = (
                    sliced_tokens[0].item() - tokenizer.timestamp_begin
                )
                end_timestamp_position = (
                    sliced_tokens[-1].item() - tokenizer.timestamp_begin
                )
                add_segment(
                    start=timestamp_offset + start_timestamp_position * time_precision,
                    end=timestamp_offset + end_timestamp_position * time_precision,
                    text_tokens=sliced_tokens[1:-1],
                    result=result,
                )
                last_slice = current_slice
            last_timestamp_position = (
                tokens[last_slice - 1].item() - tokenizer.timestamp_begin
            )
            seek += last_timestamp_position * input_stride
            all_tokens.extend(tokens[: last_slice + 1].tolist())
        else:
            duration = segment_duration
            timestamps = tokens[timestamp_tokens.nonzero().flatten()]
            if len(timestamps) > 0 and timestamps[-1].item() != tokenizer.timestamp_begin:
                # no consecutive timestamps but it has a timestamp; use the last one.
                # single timestamp at the end means no speech after the last timestamp.
                last_timestamp_position = timestamps[-1].item(
                ) - tokenizer.timestamp_begin
                duration = last_timestamp_position * time_precision

            add_segment(
                start=timestamp_offset,
                end=timestamp_offset + duration,
                text_tokens=tokens,
                result=result,
            )

            seek += segment.shape[-1]
            all_tokens.extend(tokens.tolist())

        if not condition_on_previous_text or result.temperature > 0.5:
            # do not feed the prompt tokens if a high temperature was used
            prompt_reset_since = len(all_tokens)

        previous_seek_value = seek
        progress_callback(int(min(num_frames, seek)), num_frames)

    progress_callback(num_frames, num_frames)

    return dict(text=tokenizer.decode(all_tokens[len(initial_prompt):]), segments=all_segments, language=language)
