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


def build_vocab_prompt_hint(vocab: dict[str, str]) -> str:
    """Build a prompt hint string from the correct words in the vocabulary.

    Injecting correct domain words into Whisper's initial_prompt biases the
    model toward recognising those words, improving accuracy before any
    post-processing replacement runs.
    """
    correct_words = [c.strip() for c in vocab.values() if c and c.strip()]
    if not correct_words:
        return ""
    seen: set[str] = set()
    unique_words = [w for w in correct_words if not (w in seen or seen.add(w))]
    return "、".join(unique_words)


def inject_vocab_into_prompt(existing_prompt: str, vocab: dict[str, str]) -> str:
    """Return existing_prompt with vocab hint appended (if any new terms exist)."""
    hint = build_vocab_prompt_hint(vocab)
    if not hint:
        return existing_prompt
    if existing_prompt:
        return f"{existing_prompt}、{hint}"
    return hint


def apply_vocab_to_segments(segments: list["Segment"], vocab: dict[str, str] | None = None) -> list["Segment"]:
    if vocab is None:
        vocab = load_vocab()
    if not vocab:
        return segments
    for segment in segments:
        segment.text = apply_vocab(segment.text, vocab)
    return segments
