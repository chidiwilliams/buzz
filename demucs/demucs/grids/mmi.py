# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from ._explorers import MyExplorer
from dora import Launcher


@MyExplorer
def explorer(launcher: Launcher):
    launcher.slurm_(gpus=8, time=3 * 24 * 60, partition="devlab,learnlab,learnfair")  # 3 days

    sub = launcher.bind_(
        {
            "dset": "extra_mmi_goodclean",
            "test.shifts": 0,
            "model": "htdemucs",
            "htdemucs.dconv_mode": 3,
            "htdemucs.depth": 4,
            "htdemucs.t_dropout": 0.02,
            "htdemucs.t_layers": 5,
            "max_batches": 800,
            "ema.epoch": [0.9, 0.95],
            "ema.batch": [0.9995, 0.9999],
            "dset.segment": 10,
            "batch_size": 32,
        }
    )
    sub({"model": "hdemucs"})
    sub({"model": "hdemucs", "dset": "extra44"})
    sub({"model": "hdemucs", "dset": "musdb44"})

    sparse = {
        'batch_size': 3 * 8,
        'augment.remix.group_size': 3,
        'htdemucs.t_auto_sparsity': True,
        'htdemucs.t_sparse_self_attn': True,
        'htdemucs.t_sparse_cross_attn': True,
        'htdemucs.t_sparsity': 0.9,
        "htdemucs.t_layers": 7
    }

    with launcher.job_array():
        for transf_layers in [5, 7]:
            for bottom_channels in [0, 512]:
                sub = launcher.bind({
                    "htdemucs.t_layers": transf_layers,
                    "htdemucs.bottom_channels": bottom_channels,
                })
                if bottom_channels == 0 and transf_layers == 5:
                    sub({"augment.remix.proba": 0.0})
                    sub({
                        "augment.repitch.proba": 0.0,
                        # when doing repitching, we trim the outut to align on the
                        # highest change of BPM. When removing repitching,
                        # we simulate it here to ensure the training context is the same.
                        # Another second is lost for all experiments due to the random
                        # shift augmentation.
                        "dset.segment": 10 * 0.88})
                elif bottom_channels == 512 and transf_layers == 5:
                    sub(dset="musdb44")
                    sub(dset="extra44")
                    # Sparse kernel XP, currently not released as kernels are still experimental.
                    sub(sparse, {'dset.segment': 15, "htdemucs.t_layers": 7})

                for duration in [5, 10, 15]:
                    sub({"dset.segment": duration})
