# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
"""
Main training for the Track A MDX models.
"""

from ._explorers import MyExplorer
from ..train import main

TRACK_B = ['e51eebcc', 'a1d90b5c', '5d2d6c55', 'cfa93e08']


@MyExplorer
def explorer(launcher):
    launcher.slurm_(
        gpus=8,
        time=3 * 24 * 60,
        partition='learnlab')

    # Reproduce results from MDX competition Track A
    # This trains the first round of models. Once this is trained,
    # you will need to schedule `mdx_refine`.
    for sig in TRACK_B:
        while sig is not None:
            xp = main.get_xp_from_sig(sig)
            sig = xp.cfg.continue_from

        for dset in ['extra44', 'extra_test']:
            sub = launcher.bind(xp.argv, dset=dset)
            sub()
            if dset == 'extra_test':
                sub({'quant.diffq': 1e-4})
                sub({'quant.diffq': 3e-4})
