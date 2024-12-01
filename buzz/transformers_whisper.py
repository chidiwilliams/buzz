import os
import sys
import numpy as np
import torch
import requests
from typing import Optional, Union
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from transformers.pipelines import AutomaticSpeechRecognitionPipeline
from transformers.pipelines.audio_utils import ffmpeg_read
from transformers.pipelines.automatic_speech_recognition import is_torchaudio_available


class PipelineWithProgress(AutomaticSpeechRecognitionPipeline):  # pragma: no cover
    # Copy of transformers `AutomaticSpeechRecognitionPipeline.chunk_iter` method with custom progress output
    @staticmethod
    def chunk_iter(inputs, feature_extractor, chunk_len, stride_left, stride_right, dtype=None):
        inputs_len = inputs.shape[0]
        step = chunk_len - stride_left - stride_right
        for chunk_start_idx in range(0, inputs_len, step):
            # Print progress to stderr
            progress = int((chunk_start_idx / inputs_len) * 100)
            sys.stderr.write(f"{progress}%\n")

            chunk_end_idx = chunk_start_idx + chunk_len
            chunk = inputs[chunk_start_idx:chunk_end_idx]
            processed = feature_extractor(chunk, sampling_rate=feature_extractor.sampling_rate, return_tensors="pt")
            if dtype is not None:
                processed = processed.to(dtype=dtype)
            _stride_left = 0 if chunk_start_idx == 0 else stride_left
            # all right strides must be full, otherwise it is the last item
            is_last = chunk_end_idx > inputs_len if stride_right > 0 else chunk_end_idx >= inputs_len
            _stride_right = 0 if is_last else stride_right

            chunk_len = chunk.shape[0]
            stride = (chunk_len, _stride_left, _stride_right)
            if chunk.shape[0] > _stride_left:
                yield {"is_last": is_last, "stride": stride, **processed}
            if is_last:
                break

    # Copy of transformers `AutomaticSpeechRecognitionPipeline.preprocess` method with call to custom `chunk_iter`
    def preprocess(self, inputs, chunk_length_s=0, stride_length_s=None):
        if isinstance(inputs, str):
            if inputs.startswith("http://") or inputs.startswith("https://"):
                # We need to actually check for a real protocol, otherwise it's impossible to use a local file
                # like http_huggingface_co.png
                inputs = requests.get(inputs).content
            else:
                with open(inputs, "rb") as f:
                    inputs = f.read()

        if isinstance(inputs, bytes):
            inputs = ffmpeg_read(inputs, self.feature_extractor.sampling_rate)

        stride = None
        extra = {}
        if isinstance(inputs, dict):
            stride = inputs.pop("stride", None)
            # Accepting `"array"` which is the key defined in `datasets` for
            # better integration
            if not ("sampling_rate" in inputs and ("raw" in inputs or "array" in inputs)):
                raise ValueError(
                    "When passing a dictionary to AutomaticSpeechRecognitionPipeline, the dict needs to contain a "
                    '"raw" key containing the numpy array representing the audio and a "sampling_rate" key, '
                    "containing the sampling_rate associated with that array"
                )

            _inputs = inputs.pop("raw", None)
            if _inputs is None:
                # Remove path which will not be used from `datasets`.
                inputs.pop("path", None)
                _inputs = inputs.pop("array", None)
            in_sampling_rate = inputs.pop("sampling_rate")
            extra = inputs
            inputs = _inputs
            if in_sampling_rate != self.feature_extractor.sampling_rate:
                if is_torchaudio_available():
                    from torchaudio import functional as F
                else:
                    raise ImportError(
                        "torchaudio is required to resample audio samples in AutomaticSpeechRecognitionPipeline. "
                        "The torchaudio package can be installed through: `pip install torchaudio`."
                    )

                inputs = F.resample(
                    torch.from_numpy(inputs), in_sampling_rate, self.feature_extractor.sampling_rate
                ).numpy()
                ratio = self.feature_extractor.sampling_rate / in_sampling_rate
            else:
                ratio = 1
            if stride is not None:
                if stride[0] + stride[1] > inputs.shape[0]:
                    raise ValueError("Stride is too large for input")

                # Stride needs to get the chunk length here, it's going to get
                # swallowed by the `feature_extractor` later, and then batching
                # can add extra data in the inputs, so we need to keep track
                # of the original length in the stride so we can cut properly.
                stride = (inputs.shape[0], int(round(stride[0] * ratio)), int(round(stride[1] * ratio)))
        if not isinstance(inputs, np.ndarray):
            raise ValueError(f"We expect a numpy ndarray as input, got `{type(inputs)}`")
        if len(inputs.shape) != 1:
            raise ValueError("We expect a single channel audio input for AutomaticSpeechRecognitionPipeline")

        if chunk_length_s:
            if stride_length_s is None:
                stride_length_s = chunk_length_s / 6

            if isinstance(stride_length_s, (int, float)):
                stride_length_s = [stride_length_s, stride_length_s]

            # XXX: Carefuly, this variable will not exist in `seq2seq` setting.
            # Currently chunking is not possible at this level for `seq2seq` so
            # it's ok.
            align_to = getattr(self.model.config, "inputs_to_logits_ratio", 1)
            chunk_len = int(round(chunk_length_s * self.feature_extractor.sampling_rate / align_to) * align_to)
            stride_left = int(round(stride_length_s[0] * self.feature_extractor.sampling_rate / align_to) * align_to)
            stride_right = int(round(stride_length_s[1] * self.feature_extractor.sampling_rate / align_to) * align_to)

            if chunk_len < stride_left + stride_right:
                raise ValueError("Chunk length must be superior to stride length")

            # Will use our custom chunk_iter with progress
            for item in self.chunk_iter(
                inputs, self.feature_extractor, chunk_len, stride_left, stride_right, self.torch_dtype
            ):
                yield item
        else:
            if self.type == "seq2seq_whisper" and inputs.shape[0] > self.feature_extractor.n_samples:
                processed = self.feature_extractor(
                    inputs,
                    sampling_rate=self.feature_extractor.sampling_rate,
                    truncation=False,
                    padding="longest",
                    return_tensors="pt",
                )
            else:
                processed = self.feature_extractor(
                    inputs, sampling_rate=self.feature_extractor.sampling_rate, return_tensors="pt"
                )

            if self.torch_dtype is not None:
                processed = processed.to(dtype=self.torch_dtype)
            if stride is not None:
                if self.type == "seq2seq":
                    raise ValueError("Stride is only usable with CTC models, try removing it !")

                processed["stride"] = stride
            yield {"is_last": True, **processed, **extra}


class TransformersWhisper:
    def __init__(
        self, model_id: str
    ):
        self.model_id = model_id

    def transcribe(
        self,
        audio: Union[str, np.ndarray],
        language: str,
        task: str,
        word_timestamps: bool = False,
    ):
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        use_cuda = torch.cuda.is_available() and force_cpu == "false"
        device = "cuda" if use_cuda else "cpu"
        torch_dtype = torch.float16 if use_cuda else torch.float32

        use_safetensors = True
        if os.path.exists(self.model_id):
            safetensors_files = [f for f in os.listdir(self.model_id) if f.endswith(".safetensors")]
            use_safetensors = len(safetensors_files) > 0

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=use_safetensors
        )

        model.generation_config.language = language
        model.to(device)

        processor = AutoProcessor.from_pretrained(self.model_id)

        pipe = pipeline(
            "automatic-speech-recognition",
            pipeline_class=PipelineWithProgress,
            generate_kwargs={"language": language, "task": task},
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            chunk_length_s=30,
            torch_dtype=torch_dtype,
            device=device,
        )

        transcript = pipe(audio, return_timestamps="word" if word_timestamps else True)

        segments = []
        for chunk in transcript['chunks']:
            start, end = chunk['timestamp']
            text = chunk['text']
            segments.append({
                "start": 0 if start is None else start,
                "end": 0 if end is None else end,
                "text": text,
                "translation": ""
            })

        return {
            "text": transcript['text'],
            "segments": segments,
        }

