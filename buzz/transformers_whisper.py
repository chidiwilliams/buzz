import os
import sys
import logging
import platform
import numpy as np
import torch
import requests
from typing import Union
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline, BitsAndBytesConfig
from transformers.pipelines import AutomaticSpeechRecognitionPipeline
from transformers.pipelines.audio_utils import ffmpeg_read
from transformers.pipelines.automatic_speech_recognition import is_torchaudio_available

from buzz.model_loader import is_mms_model, map_language_to_mms


def is_intel_mac() -> bool:
    """Check if running on Intel Mac (x86_64)."""
    return sys.platform == 'darwin' and platform.machine() == 'x86_64'


def is_peft_model(model_id: str) -> bool:
    """Check if model is a PEFT model based on model ID containing '-peft'."""
    return "-peft" in model_id.lower()


class PipelineWithProgress(AutomaticSpeechRecognitionPipeline):  # pragma: no cover
    # Copy of transformers `AutomaticSpeechRecognitionPipeline.chunk_iter` method with custom progress output
    @staticmethod
    def chunk_iter(inputs, feature_extractor, chunk_len, stride_left, stride_right, dtype=None):
        inputs_len = inputs.shape[0]
        step = chunk_len - stride_left - stride_right
        for chunk_start_idx in range(0, inputs_len, step):

            # Buzz will print progress to stderr
            progress = int((chunk_start_idx / inputs_len) * 100)
            sys.stderr.write(f"{progress}%\n")

            chunk_end_idx = chunk_start_idx + chunk_len
            chunk = inputs[chunk_start_idx:chunk_end_idx]
            processed = feature_extractor(chunk, sampling_rate=feature_extractor.sampling_rate, return_tensors="pt")
            if dtype is not None:
                processed = processed.to(dtype=dtype)
            _stride_left = 0 if chunk_start_idx == 0 else stride_left
            is_last = chunk_end_idx >= inputs_len
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
            raise TypeError(f"We expect a numpy ndarray as input, got `{type(inputs)}`")
        if len(inputs.shape) != 1:
            raise ValueError("We expect a single channel audio input for AutomaticSpeechRecognitionPipeline")

        if chunk_length_s:
            if stride_length_s is None:
                stride_length_s = chunk_length_s / 6

            if isinstance(stride_length_s, (int, float)):
                stride_length_s = [stride_length_s, stride_length_s]

            # XXX: Carefully, this variable will not exist in `seq2seq` setting.
            # Currently chunking is not possible at this level for `seq2seq` so
            # it's ok.
            align_to = getattr(self.model.config, "inputs_to_logits_ratio", 1)
            chunk_len = int(round(chunk_length_s * self.feature_extractor.sampling_rate / align_to) * align_to)
            stride_left = int(round(stride_length_s[0] * self.feature_extractor.sampling_rate / align_to) * align_to)
            stride_right = int(round(stride_length_s[1] * self.feature_extractor.sampling_rate / align_to) * align_to)

            if chunk_len < stride_left + stride_right:
                raise ValueError("Chunk length must be superior to stride length")

            # Buzz use our custom chunk_iter with progress
            for item in self.chunk_iter(
                inputs, self.feature_extractor, chunk_len, stride_left, stride_right, self.torch_dtype
            ):
                yield {**item, **extra}
        else:
            if self.type == "seq2seq_whisper" and inputs.shape[0] > self.feature_extractor.n_samples:
                processed = self.feature_extractor(
                    inputs,
                    sampling_rate=self.feature_extractor.sampling_rate,
                    truncation=False,
                    padding="longest",
                    return_tensors="pt",
                    return_attention_mask=True,
                )
            else:
                if self.type == "seq2seq_whisper" and stride is None:
                    processed = self.feature_extractor(
                        inputs,
                        sampling_rate=self.feature_extractor.sampling_rate,
                        return_tensors="pt",
                        return_token_timestamps=True,
                        return_attention_mask=True,
                    )
                    extra["num_frames"] = processed.pop("num_frames")
                else:
                    processed = self.feature_extractor(
                        inputs,
                        sampling_rate=self.feature_extractor.sampling_rate,
                        return_tensors="pt",
                        return_attention_mask=True,
                    )
            if self.torch_dtype is not None:
                processed = processed.to(dtype=self.torch_dtype)
            if stride is not None:
                if self.type == "seq2seq":
                    raise ValueError("Stride is only usable with CTC models, try removing it !")

                processed["stride"] = stride
            yield {"is_last": True, **processed, **extra}


class TransformersTranscriber:
    """Unified transcriber for HuggingFace models (Whisper and MMS)."""

    def __init__(self, model_id: str):
        self.model_id = model_id
        self._is_mms = is_mms_model(model_id)
        self._is_peft = is_peft_model(model_id)

    @property
    def is_mms_model(self) -> bool:
        """Returns True if this is an MMS model."""
        return self._is_mms

    @property
    def is_peft_model(self) -> bool:
        """Returns True if this is a PEFT model."""
        return self._is_peft

    def transcribe(
        self,
        audio: Union[str, np.ndarray],
        language: str,
        task: str,
        word_timestamps: bool = False,
    ):
        """Transcribe audio using either Whisper or MMS model."""
        if self._is_mms:
            return self._transcribe_mms(audio, language)
        else:
            return self._transcribe_whisper(audio, language, task, word_timestamps)

    def _transcribe_whisper(
        self,
        audio: Union[str, np.ndarray],
        language: str,
        task: str,
        word_timestamps: bool = False,
    ):
        """Transcribe using Whisper model."""
        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        use_cuda = torch.cuda.is_available() and force_cpu == "false"
        device = "cuda" if use_cuda else "cpu"
        torch_dtype = torch.float16 if use_cuda else torch.float32

        # Check if this is a PEFT model
        if is_peft_model(self.model_id):
            model, processor, use_8bit = self._load_peft_model(device, torch_dtype)
        else:
            use_safetensors = True
            if os.path.exists(self.model_id):
                safetensors_files = [f for f in os.listdir(self.model_id) if f.endswith(".safetensors")]
                use_safetensors = len(safetensors_files) > 0

            # Check if user wants reduced GPU memory usage (8-bit quantization)
            # Skip on Intel Macs as bitsandbytes is not available there
            reduce_gpu_memory = os.getenv("BUZZ_REDUCE_GPU_MEMORY", "false") != "false"
            use_8bit = False
            if device == "cuda" and reduce_gpu_memory and not is_intel_mac():
                try:
                    import bitsandbytes  # noqa: F401
                    use_8bit = True
                    print("Using 8-bit quantization for reduced GPU memory usage")
                except ImportError:
                    print("bitsandbytes not available, using standard precision")

            if use_8bit:
                quantization_config = BitsAndBytesConfig(load_in_8bit=True)
                model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    self.model_id,
                    quantization_config=quantization_config,
                    device_map="auto",
                    use_safetensors=use_safetensors
                )
            else:
                model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    self.model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=use_safetensors
                )
                model.to(device)

            model.generation_config.language = language

            processor = AutoProcessor.from_pretrained(self.model_id)

        pipeline_kwargs = {
            "task": "automatic-speech-recognition",
            "pipeline_class": PipelineWithProgress,
            "generate_kwargs": {
                "language": language,
                "task": task,
                "no_repeat_ngram_size": 3,
                "repetition_penalty": 1.2,
            },
            "model": model,
            "tokenizer": processor.tokenizer,
            "feature_extractor": processor.feature_extractor,
            # pipeline has built in chunking, works faster, but we loose progress output
            # needed for word level timestamps, otherwise there is huge RAM usage on longer audios
            "chunk_length_s": 30 if word_timestamps else None,
            "torch_dtype": torch_dtype,
            "ignore_warning": True,  # Ignore warning about chunk_length_s being experimental for seq2seq models
        }
        if not use_8bit:
            pipeline_kwargs["device"] = device
        pipe = pipeline(**pipeline_kwargs)

        transcript = pipe(
            audio,
            return_timestamps="word" if word_timestamps else True,
        )

        segments = []
        for chunk in transcript['chunks']:
            start, end = chunk['timestamp']
            text = chunk['text']

            # Last segment may not have an end timestamp
            if start is None:
                start = 0
            if end is None:
                end = start + 0.1

            if end > start and text.strip() != "":
                segments.append({
                    "start": 0 if start is None else start,
                    "end": 0 if end is None else end,
                    "text": text.strip(),
                    "translation": ""
                })

        return {
            "text": transcript['text'],
            "segments": segments,
        }

    def _load_peft_model(self, device: str, torch_dtype):
        """Load a PEFT (Parameter-Efficient Fine-Tuning) model.

        PEFT models require loading the base model first, then applying the adapter.
        The base model path is extracted from the PEFT config.

        Returns:
            Tuple of (model, processor, use_8bit)
        """
        from peft import PeftModel, PeftConfig
        from transformers import WhisperForConditionalGeneration, WhisperFeatureExtractor, WhisperTokenizer

        print(f"Loading PEFT model: {self.model_id}")

        # Get the PEFT model ID (handle both local paths and repo IDs)
        peft_model_id = self._get_peft_repo_id()

        # Load PEFT config to get base model path
        peft_config = PeftConfig.from_pretrained(peft_model_id)
        base_model_path = peft_config.base_model_name_or_path
        print(f"PEFT base model: {base_model_path}")

        # Load the base Whisper model
        # Use 8-bit quantization on CUDA if user enabled "Reduce GPU RAM" and bitsandbytes is available
        # Skip on Intel Macs as bitsandbytes is not available there
        reduce_gpu_memory = os.getenv("BUZZ_REDUCE_GPU_MEMORY", "false") != "false"
        use_8bit = False
        if device == "cuda" and reduce_gpu_memory and not is_intel_mac():
            try:
                import bitsandbytes  # noqa: F401
                use_8bit = True
                print("Using 8-bit quantization for reduced GPU memory usage")
            except ImportError:
                print("bitsandbytes not available, using standard precision for PEFT model")

        if use_8bit:
            quantization_config = BitsAndBytesConfig(load_in_8bit=True)
            model = WhisperForConditionalGeneration.from_pretrained(
                base_model_path,
                quantization_config=quantization_config,
                device_map="auto"
            )
        else:
            model = WhisperForConditionalGeneration.from_pretrained(
                base_model_path,
                torch_dtype=torch_dtype,
                low_cpu_mem_usage=True
            )
            model.to(device)

        # Apply the PEFT adapter
        model = PeftModel.from_pretrained(model, peft_model_id)
        model.config.use_cache = True

        # Load feature extractor and tokenizer from base model
        feature_extractor = WhisperFeatureExtractor.from_pretrained(base_model_path)
        tokenizer = WhisperTokenizer.from_pretrained(base_model_path, task="transcribe")

        # Create a simple processor-like object that the pipeline expects
        class PeftProcessor:
            def __init__(self, feature_extractor, tokenizer):
                self.feature_extractor = feature_extractor
                self.tokenizer = tokenizer

        processor = PeftProcessor(feature_extractor, tokenizer)

        return model, processor, use_8bit

    def _get_peft_repo_id(self) -> str:
        """Extract HuggingFace repo ID from local cache path for PEFT models."""
        model_id = self.model_id

        # If it's already a repo ID (contains / but not a file path), return as-is
        if "/" in model_id and not os.path.exists(model_id):
            return model_id

        # Extract repo ID from cache path
        if "models--" in model_id:
            parts = model_id.split("models--")
            if len(parts) > 1:
                repo_part = parts[1].split(os.sep + "snapshots")[0]
                repo_id = repo_part.replace("--", "/", 1)
                return repo_id

        # Fallback: return as-is
        return model_id

    def _get_mms_repo_id(self) -> str:
        """Extract HuggingFace repo ID from local cache path or return as-is if already a repo ID."""
        model_id = self.model_id

        # If it's already a repo ID (contains / but not a file path), return as-is
        if "/" in model_id and not os.path.exists(model_id):
            return model_id

        # Extract repo ID from cache path like:
        # Linux: /home/user/.cache/Buzz/models/models--facebook--mms-1b-all/snapshots/xxx
        # Windows: C:\Users\user\.cache\Buzz\models\models--facebook--mms-1b-all\snapshots\xxx
        if "models--" in model_id:
            # Extract the part after "models--" and before "/snapshots" or "\snapshots"
            parts = model_id.split("models--")
            if len(parts) > 1:
                # Split on os.sep to handle both Windows and Unix paths
                repo_part = parts[1].split(os.sep + "snapshots")[0]
                # Convert facebook--mms-1b-all to facebook/mms-1b-all
                repo_id = repo_part.replace("--", "/", 1)
                return repo_id

        # Fallback: return as-is
        return model_id

    def _transcribe_mms(
        self,
        audio: Union[str, np.ndarray],
        language: str,
    ):
        """Transcribe using MMS (Massively Multilingual Speech) model."""
        from transformers import Wav2Vec2ForCTC, AutoProcessor as MMSAutoProcessor
        from transformers.pipelines.audio_utils import ffmpeg_read as mms_ffmpeg_read

        force_cpu = os.getenv("BUZZ_FORCE_CPU", "false")
        use_cuda = torch.cuda.is_available() and force_cpu == "false"
        device = "cuda" if use_cuda else "cpu"

        # Map language code to ISO 639-3 for MMS
        mms_language = map_language_to_mms(language)
        print(f"MMS transcription with language: {mms_language} (original: {language})")

        sys.stderr.write("0%\n")

        # Use repo ID for MMS to allow adapter downloads
        # Local paths don't work for adapter downloads
        repo_id = self._get_mms_repo_id()
        print(f"MMS using repo ID: {repo_id} (from model_id: {self.model_id})")

        # Load processor and model with target language
        # This will download the language adapter if not cached
        processor = MMSAutoProcessor.from_pretrained(
            repo_id,
            target_lang=mms_language
        )

        model = Wav2Vec2ForCTC.from_pretrained(
            repo_id,
            target_lang=mms_language,
            ignore_mismatched_sizes=True
        )
        model.to(device)

        sys.stderr.write("25%\n")

        # Load and process audio
        if isinstance(audio, str):
            with open(audio, "rb") as f:
                audio_data = f.read()
            audio_array = mms_ffmpeg_read(audio_data, processor.feature_extractor.sampling_rate)
        else:
            audio_array = audio

        # Ensure audio is the right sample rate
        sampling_rate = processor.feature_extractor.sampling_rate

        sys.stderr.write("50%\n")

        # Process audio in chunks for progress reporting
        inputs = processor(
            audio_array,
            sampling_rate=sampling_rate,
            return_tensors="pt",
            padding=True
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        sys.stderr.write("75%\n")

        # Run inference
        with torch.no_grad():
            outputs = model(**inputs).logits

        # Decode
        ids = torch.argmax(outputs, dim=-1)[0]
        transcription = processor.decode(ids)

        sys.stderr.write("100%\n")

        # Calculate approximate duration for segment
        duration = len(audio_array) / sampling_rate if isinstance(audio_array, np.ndarray) else 0

        # Return in same format as Whisper for consistency
        # MMS doesn't provide word-level timestamps, so we return a single segment
        return {
            "text": transcription,
            "segments": [{
                "start": 0,
                "end": duration,
                "text": transcription.strip(),
                "translation": ""
            }] if transcription.strip() else []
        }


# Alias for backward compatibility
TransformersWhisper = TransformersTranscriber

