# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from ._explorers import MyExplorer
from dora import Launcher


@MyExplorer
def explorer(launcher: Launcher):
    launcher.slurm_(gpus=8, time=3 * 24 * 60, partition="speechgpt,learnfair",
                    mem_per_gpu=None, constraint='')
    launcher.bind_({"dset.use_musdb": False})

    with launcher.job_array():
        launcher(dset='sdx23_bleeding')
        launcher(dset='sdx23_labelnoise')
