"""Keep NeMo's diarization from running out of memory on long recordings."""

import importlib
import logging
from typing import List

# Each batch needs a few hundred MB at most, even for recordings many hours long.
BASE_SEGMENTS_PER_BATCH = 1024

# NeMo modules holding a reference to get_argmin_mat. The ones that import it by
# name keep their own reference, so each of them has to be replaced.
MODULES_USING_GET_ARGMIN_MAT = (
    "nemo.collections.asr.parts.utils.offline_clustering",
    "nemo.collections.asr.parts.utils.speaker_utils",
    "nemo.collections.asr.data.audio_to_diar_label",
)


def get_argmin_mat(timestamps_in_scales: List["torch.Tensor"]) -> List["torch.Tensor"]:
    """Map each base scale segment to the closest segment of every scale.

    Gives the same result as NeMo's function of this name, which compares all
    the segments at once. That takes four temporary matrices of
    (base segments x scale segments) floats, about 7 GB for two hours of speech.
    """
    import torch

    anchors = [torch.mean(timestamps, dim=1) for timestamps in timestamps_in_scales]
    base_anchors = anchors[-1]

    return [
        torch.cat(
            [
                torch.argmin(torch.abs(scale_anchors - batch.unsqueeze(1)), dim=1)
                for batch in torch.split(base_anchors, BASE_SEGMENTS_PER_BATCH)
            ]
        )
        for scale_anchors in anchors
    ]


def patch_nemo_memory_use() -> None:
    """Replace NeMo's get_argmin_mat. Call this before running a diarizer.

    This only saves memory, so a NeMo release that moved the function must not
    stop diarization: its own function still works.
    """
    for module_name in MODULES_USING_GET_ARGMIN_MAT:
        try:
            module = importlib.import_module(module_name)
        except ImportError as error:
            logging.warning("Cannot limit NeMo memory use in %s: %s", module_name, error)
            continue
        if not hasattr(module, "get_argmin_mat"):
            logging.warning("Cannot limit NeMo memory use: %s has no get_argmin_mat", module_name)
            continue
        module.get_argmin_mat = get_argmin_mat
