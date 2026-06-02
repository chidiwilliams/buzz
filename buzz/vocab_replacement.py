import json
import logging
import os
from typing import TYPE_CHECKING

from platformdirs import user_data_dir

if TYPE_CHECKING:
    from buzz.transcriber.transcriber import Segment


def get_vocab_file_path() -> str:
    return os.path.join(user_data_dir("Buzz", "Buzz"), "vocabulary.json")


def load_vocab() -> dict[str, str]:
    path = get_vocab_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        logging.warning("Failed to load vocabulary file", exc_info=True)
        return {}


def save_vocab(vocab: dict[str, str]) -> None:
    path = get_vocab_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)


def apply_vocab(text: str, vocab: dict[str, str]) -> str:
    for wrong, correct in vocab.items():
        if wrong:
            text = text.replace(wrong, correct)
    return text


def apply_vocab_to_segments(segments: list["Segment"], vocab: dict[str, str] | None = None) -> list["Segment"]:
    if vocab is None:
        vocab = load_vocab()
    if not vocab:
        return segments
    for segment in segments:
        segment.text = apply_vocab(segment.text, vocab)
    return segments
