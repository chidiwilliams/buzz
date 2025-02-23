# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
"""
Fine tuning experiments
"""

from ._explorers import MyExplorer
from ..train import main


@MyExplorer
def explorer(launcher):
    launcher.slurm_(
        gpus=8,
        time=300,
        partition='devlab,learnlab')

    # Mus
    launcher.slurm_(constraint='volta32gb')

    grid = "repro"
    folder = main.dora.dir / "grids" / grid

    for sig in folder.iterdir():
        if not sig.is_symlink():
            continue
        xp = main.get_xp_from_sig(sig)
        xp.link.load()
        if len(xp.link.history) != xp.cfg.epochs:
            continue
        sub = launcher.bind(xp.argv, [f'continue_from="{xp.sig}"'])
        sub.bind_({'ema.epoch': [0.9, 0.95], 'ema.batch': [0.9995, 0.9999]})
        sub.bind_({'test.every': 1, 'test.sdr': True, 'epochs': 4})
        sub.bind_({'dset.segment': 28, 'dset.shift': 2})
        sub.bind_({'batch_size': 32})
        auto = {'dset': 'auto_mus'}
        auto.update({'augment.remix.proba': 0, 'augment.scale.proba': 0,
                     'augment.shift_same': True})
        sub.bind_(auto)
        sub.bind_({'batch_size': 16})
        sub.bind_({'optim.lr': 1e-4})
        sub.bind_({'model_segment': 44})
        sub()
