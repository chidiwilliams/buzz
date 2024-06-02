import sys
import logging
from typing import Optional, Union

import numpy as np
from tqdm import tqdm

import whisper
import torch
from transformers import WhisperProcessor, WhisperForConditionalGeneration

def cuda_is_viable(min_vram_gb=10):
    if not torch.cuda.is_available():
        return False

    total_memory = torch.cuda.get_device_properties(0).total_memory / 1e9  # Convert bytes to GB
    if total_memory < min_vram_gb:
        return False

    return True


def load_model(model_name_or_path: str):
    processor = WhisperProcessor.from_pretrained(model_name_or_path)
    model = WhisperForConditionalGeneration.from_pretrained(model_name_or_path)

    if cuda_is_viable():
        logging.debug("CUDA is available and has enough VRAM, moving model to GPU.")
        model.to("cuda")

    return TransformersWhisper(processor, model)


class TransformersWhisper:
    def __init__(
        self, processor: WhisperProcessor, model: WhisperForConditionalGeneration
    ):
        self.processor = processor
        self.model = model
        self.SAMPLE_RATE = whisper.audio.SAMPLE_RATE
        self.N_SAMPLES_IN_CHUNK = whisper.audio.N_SAMPLES

    # Patch implementation of transcribing with transformers' WhisperProcessor until long-form transcription and
    # timestamps are available. See: https://github.com/huggingface/transformers/issues/19887,
    # https://github.com/huggingface/transformers/pull/20620.
    def transcribe(
        self,
        audio: Union[str, np.ndarray],
        language: str,
        task: str,
        verbose: Optional[bool] = None,
    ):
        if isinstance(audio, str):
            audio = whisper.load_audio(audio, sr=self.SAMPLE_RATE)

        self.model.config.forced_decoder_ids = self.processor.get_decoder_prompt_ids(
            task=task, language=language
        )

        segments = []
        all_predicted_ids = []

        num_samples = audio.size
        seek = 0
        with tqdm(
            total=num_samples, unit="samples", disable=verbose is not False
        ) as progress_bar:
            while seek < num_samples:
                chunk = audio[seek : seek + self.N_SAMPLES_IN_CHUNK]
                input_features = self.processor(
                    chunk, return_tensors="pt", sampling_rate=self.SAMPLE_RATE
                ).input_features.to(self.model.device)
                predicted_ids = self.model.generate(input_features)
                all_predicted_ids.extend(predicted_ids)
                text: str = self.processor.batch_decode(
                    predicted_ids, skip_special_tokens=True
                )[0]
                if text.strip() != "":
                    segments.append(
                        {
                            "start": seek / self.SAMPLE_RATE,
                            "end": min(seek + self.N_SAMPLES_IN_CHUNK, num_samples)
                            / self.SAMPLE_RATE,
                            "text": text,
                        }
                    )

                progress_bar.update(
                    min(seek + self.N_SAMPLES_IN_CHUNK, num_samples) - seek
                )
                seek += self.N_SAMPLES_IN_CHUNK

        return {
            "text": self.processor.batch_decode(
                all_predicted_ids, skip_special_tokens=True
            )[0],
            "segments": segments,
        }
