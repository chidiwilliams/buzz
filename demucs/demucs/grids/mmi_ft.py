# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from ._explorers import MyExplorer
from dora import Launcher
from demucs import train


def get_sub(launcher, sig):
    xp = train.main.get_xp_from_sig(sig)
    sub = launcher.bind(xp.argv)
    sub()
    sub.bind_({
        'continue_from': sig,
        'continue_best': True})
    return sub


@MyExplorer
def explorer(launcher: Launcher):
    launcher.slurm_(gpus=4, time=3 * 24 * 60, partition="devlab,learnlab,learnfair")  # 3 days
    ft = {
        'optim.lr': 1e-4,
        'augment.remix.proba': 0,
        'augment.scale.proba': 0,
        'augment.shift_same': True,
        'htdemucs.t_weight_decay': 0.05,
        'batch_size': 8,
        'optim.clip_grad': 5,
        'optim.optim': 'adamw',
        'epochs': 50,
        'dset.wav2_valid': True,
        'ema.epoch': [],  # let's make valid a bit faster
    }
    with launcher.job_array():
        for sig in ['2899e11a']:
            sub = get_sub(launcher, sig)
            sub.bind_(ft)
            for segment in [15, 18]:
                for source in range(4):
                    w = [0] * 4
                    w[source] = 1
                    sub({'weights': w, 'dset.segment': segment})

        for sig in ['955717e8']:
            sub = get_sub(launcher, sig)
            sub.bind_(ft)
            for segment in [10, 15]:
                for source in range(4):
                    w = [0] * 4
                    w[source] = 1
                    sub({'weights': w, 'dset.segment': segment})
