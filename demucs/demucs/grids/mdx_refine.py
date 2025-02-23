# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
"""
Main training for the Track A MDX models.
"""

from ._explorers import MyExplorer
from .mdx import TRACK_A
from ..train import main


@MyExplorer
def explorer(launcher):
    launcher.slurm_(
        gpus=8,
        time=3 * 24 * 60,
        partition='learnlab')

    # Reproduce results from MDX competition Track A
    # WARNING: all the experiments in the `mdx` grid must have completed.
    for sig in TRACK_A:
        xp = main.get_xp_from_sig(sig)
        launcher(xp.argv)
        for diffq in [1e-4, 3e-4]:
            xp_src = main.get_xp_from_sig(xp.cfg.continue_from)
            q_argv = [f'quant.diffq={diffq}']
            actual_src = main.get_xp(xp_src.argv + q_argv)
            actual_src.link.load()
            assert len(actual_src.link.history) == actual_src.cfg.epochs
            argv = xp.argv + q_argv + [f'continue_from="{actual_src.sig}"']
            launcher(argv)
