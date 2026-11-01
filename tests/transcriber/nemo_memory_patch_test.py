import sys
import types

import pytest
import torch

from buzz.transcriber import nemo_memory_patch
from buzz.transcriber.nemo_memory_patch import get_argmin_mat, patch_nemo_memory_use


def nemo_get_argmin_mat(timestamps_in_scales):
    """NeMo's original implementation, which the replacement has to match."""
    anchors = [torch.mean(timestamps, dim=1) for timestamps in timestamps_in_scales]
    base_anchor = anchors[-1]
    mappings = []
    for curr_anchor in anchors:
        curr_mat = torch.tile(curr_anchor, (base_anchor.shape[0], 1))
        base_mat = torch.tile(base_anchor, (curr_anchor.shape[0], 1)).t()
        mappings.append(torch.argmin(torch.abs(curr_mat - base_mat), dim=1))
    return mappings


def scale(window, shift, count):
    starts = torch.arange(count, dtype=torch.float32) * shift
    return torch.stack([starts, starts + window], dim=1)


def assert_matches_nemo(timestamps_in_scales):
    expected = nemo_get_argmin_mat(timestamps_in_scales)
    actual = get_argmin_mat(timestamps_in_scales)

    assert len(actual) == len(expected)
    for actual_mapping, expected_mapping in zip(actual, expected):
        assert actual_mapping.dtype == expected_mapping.dtype
        assert torch.equal(actual_mapping, expected_mapping)


class TestGetArgminMat:
    def test_matches_nemo_across_scales(self):
        assert_matches_nemo([scale(1.5, 0.75, 400), scale(1.0, 0.5, 600), scale(0.5, 0.25, 1200)])

    def test_matches_nemo_when_nearest_segments_are_tied(self):
        # Base anchors fall exactly between two anchors of the longer scale
        assert_matches_nemo([scale(1.0, 1.0, 50), scale(0.5, 0.5, 100)])

    def test_matches_nemo_on_unordered_segments(self):
        generator = torch.Generator().manual_seed(0)
        assert_matches_nemo(
            [
                torch.rand(300, 2, generator=generator) * 100,
                torch.rand(700, 2, generator=generator) * 100,
            ]
        )

    def test_matches_nemo_across_batch_boundaries(self, monkeypatch):
        monkeypatch.setattr(nemo_memory_patch, "BASE_SEGMENTS_PER_BATCH", 7)
        assert_matches_nemo([scale(1.5, 0.75, 20), scale(0.5, 0.25, 60)])

    def test_never_compares_more_than_one_batch_at_once(self, monkeypatch):
        monkeypatch.setattr(nemo_memory_patch, "BASE_SEGMENTS_PER_BATCH", 10)
        real_argmin = torch.argmin
        compared_shapes = []

        def recording_argmin(input, *args, **kwargs):
            compared_shapes.append(input.shape)
            return real_argmin(input, *args, **kwargs)

        monkeypatch.setattr(torch, "argmin", recording_argmin)
        get_argmin_mat([scale(0.5, 0.25, 35)])

        assert [shape[0] for shape in compared_shapes] == [10, 10, 10, 5]


class TestPatchNemoMemoryUse:
    def test_missing_function_or_module_only_logs_a_warning(self, monkeypatch, caplog):
        present = types.ModuleType("present")
        present.get_argmin_mat = "original"
        without_function = types.ModuleType("without_function")
        monkeypatch.setitem(sys.modules, "present", present)
        monkeypatch.setitem(sys.modules, "without_function", without_function)
        monkeypatch.setattr(
            nemo_memory_patch,
            "MODULES_USING_GET_ARGMIN_MAT",
            ("without_function", "buzz_module_that_does_not_exist", "present"),
        )

        patch_nemo_memory_use()

        assert not hasattr(without_function, "get_argmin_mat")
        assert present.get_argmin_mat is get_argmin_mat
        assert "without_function" in caplog.text
        assert "buzz_module_that_does_not_exist" in caplog.text

    def test_replaces_every_reference_nemo_holds(self, monkeypatch):
        offline_clustering = pytest.importorskip(
            "nemo.collections.asr.parts.utils.offline_clustering"
        )
        speaker_utils = pytest.importorskip("nemo.collections.asr.parts.utils.speaker_utils")
        audio_to_diar_label = pytest.importorskip("nemo.collections.asr.data.audio_to_diar_label")
        modules = (offline_clustering, speaker_utils, audio_to_diar_label)
        for module in modules:
            monkeypatch.setattr(module, "get_argmin_mat", module.get_argmin_mat)

        patch_nemo_memory_use()

        assert all(module.get_argmin_mat is get_argmin_mat for module in modules)

    def test_uses_replacement_in_nemo_interpolation(self, monkeypatch):
        offline_clustering = pytest.importorskip(
            "nemo.collections.asr.parts.utils.offline_clustering"
        )
        monkeypatch.setattr(
            offline_clustering, "get_argmin_mat", offline_clustering.get_argmin_mat
        )
        timestamps = [scale(1.0, 0.5, 20), scale(0.5, 0.25, 40)]
        embeddings = [torch.rand(20, 4), torch.rand(40, 4)]
        weights = torch.tensor([[1.0, 1.0]])
        expected, expected_mapping = offline_clustering.get_scale_interpolated_embs(
            weights, embeddings, timestamps
        )

        patch_nemo_memory_use()
        actual, actual_mapping = offline_clustering.get_scale_interpolated_embs(
            weights, embeddings, timestamps
        )

        assert torch.equal(actual, expected)
        assert all(torch.equal(a, e) for a, e in zip(actual_mapping, expected_mapping))
