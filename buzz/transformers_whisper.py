from typing import Optional, Union

import numpy as np
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline


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
    ):

        device = "cuda" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.model_id, torch_dtype=torch_dtype, use_safetensors=True
        )

        model.generation_config.language = language
        model.to(device)

        processor = AutoProcessor.from_pretrained(self.model_id)

        pipe = pipeline(
            "automatic-speech-recognition",
            generate_kwargs={"language": language, "task": task},
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            chunk_length_s=30,
            torch_dtype=torch_dtype,
            device=device,
        )

        transcript = pipe(audio, return_timestamps=True)

        segments = []
        for chunk in transcript['chunks']:
            start, end = chunk['timestamp']
            text = chunk['text']
            segments.append({
                "start": start,
                "end": end,
                "text": text,
                "translation": ""
            })

        return {
            "text": transcript['text'],
            "segments": segments,
        }

