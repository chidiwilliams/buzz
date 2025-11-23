#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
"""Main training script entry point"""

import logging
import os
from pathlib import Path
import sys

from dora import hydra_main
import hydra
from hydra.core.global_hydra import GlobalHydra
from omegaconf import OmegaConf
from . import audio_legacy
import torch
from torch import nn
import torchaudio
from torch.utils.data import ConcatDataset

from . import distrib
from .wav import get_wav_datasets, get_musdb_wav_datasets
from .demucs import Demucs
from .hdemucs import HDemucs
from .htdemucs import HTDemucs
from .repitch import RepitchedWrapper
from .solver import Solver
from .states import capture_init
from .utils import random_subset

logger = logging.getLogger(__name__)


class TorchHDemucsWrapper(nn.Module):
    """Wrapper around torchaudio HDemucs implementation to provide the proper metadata
    for model evaluation.
    See https://pytorch.org/audio/stable/tutorials/hybrid_demucs_tutorial.html"""

    @capture_init
    def __init__(self,  **kwargs):
        super().__init__()
        try:
            from torchaudio.models import HDemucs as TorchHDemucs
        except ImportError:
            raise ImportError("Please upgrade torchaudio for using its implementation of HDemucs")
        self.samplerate = kwargs.pop('samplerate')
        self.segment = kwargs.pop('segment')
        self.sources = kwargs['sources']
        self.torch_hdemucs = TorchHDemucs(**kwargs)

    def forward(self, mix):
        return self.torch_hdemucs.forward(mix)


def get_model(args):
    extra = {
        'sources': list(args.dset.sources),
        'audio_channels': args.dset.channels,
        'samplerate': args.dset.samplerate,
        'segment': args.model_segment or 4 * args.dset.segment,
    }
    klass = {
        'demucs': Demucs,
        'hdemucs': HDemucs,
        'htdemucs': HTDemucs,
        'torch_hdemucs': TorchHDemucsWrapper,
    }[args.model]
    kw = OmegaConf.to_container(getattr(args, args.model), resolve=True)
    model = klass(**extra, **kw)
    return model


def get_optimizer(model, args):
    seen_params = set()
    other_params = []
    groups = []
    for n, module in model.named_modules():
        if hasattr(module, "make_optim_group"):
            group = module.make_optim_group()
            params = set(group["params"])
            assert params.isdisjoint(seen_params)
            seen_params |= set(params)
            groups.append(group)
    for param in model.parameters():
        if param not in seen_params:
            other_params.append(param)
    groups.insert(0, {"params": other_params})
    parameters = groups
    if args.optim.optim == "adam":
        return torch.optim.Adam(
            parameters,
            lr=args.optim.lr,
            betas=(args.optim.momentum, args.optim.beta2),
            weight_decay=args.optim.weight_decay,
        )
    elif args.optim.optim == "adamw":
        return torch.optim.AdamW(
            parameters,
            lr=args.optim.lr,
            betas=(args.optim.momentum, args.optim.beta2),
            weight_decay=args.optim.weight_decay,
        )
    else:
        raise ValueError("Invalid optimizer %s", args.optim.optimizer)


def get_datasets(args):
    if args.dset.backend:
        torchaudio.set_audio_backend(args.dset.backend)
    if args.dset.use_musdb:
        train_set, valid_set = get_musdb_wav_datasets(args.dset)
    else:
        train_set, valid_set = [], []
    if args.dset.wav:
        extra_train_set, extra_valid_set = get_wav_datasets(args.dset)
        if len(args.dset.sources) <= 4:
            train_set = ConcatDataset([train_set, extra_train_set])
            valid_set = ConcatDataset([valid_set, extra_valid_set])
        else:
            train_set = extra_train_set
            valid_set = extra_valid_set

    if args.dset.wav2:
        extra_train_set, extra_valid_set = get_wav_datasets(args.dset, "wav2")
        weight = args.dset.wav2_weight
        if weight is not None:
            b = len(train_set)
            e = len(extra_train_set)
            reps = max(1, round(e / b * (1 / weight - 1)))
        else:
            reps = 1
        train_set = ConcatDataset([train_set] * reps + [extra_train_set])
        if args.dset.wav2_valid:
            if weight is not None:
                b = len(valid_set)
                n_kept = int(round(weight * b / (1 - weight)))
                valid_set = ConcatDataset(
                    [valid_set, random_subset(extra_valid_set, n_kept)]
                )
            else:
                valid_set = ConcatDataset([valid_set, extra_valid_set])
    if args.dset.valid_samples is not None:
        valid_set = random_subset(valid_set, args.dset.valid_samples)
    assert len(train_set)
    assert len(valid_set)
    return train_set, valid_set


def get_solver(args, model_only=False):
    distrib.init()

    torch.manual_seed(args.seed)
    model = get_model(args)
    if args.misc.show:
        logger.info(model)
        mb = sum(p.numel() for p in model.parameters()) * 4 / 2**20
        logger.info('Size: %.1f MB', mb)
        if hasattr(model, 'valid_length'):
            field = model.valid_length(1)
            logger.info('Field: %.1f ms', field / args.dset.samplerate * 1000)
        sys.exit(0)

    # torch also initialize cuda seed if available
    if torch.cuda.is_available():
        model.cuda()

    # optimizer
    optimizer = get_optimizer(model, args)

    assert args.batch_size % distrib.world_size == 0
    args.batch_size //= distrib.world_size

    if model_only:
        return Solver(None, model, optimizer, args)

    train_set, valid_set = get_datasets(args)

    if args.augment.repitch.proba:
        vocals = []
        if 'vocals' in args.dset.sources:
            vocals.append(args.dset.sources.index('vocals'))
        else:
            logger.warning('No vocal source found')
        if args.augment.repitch.proba:
            train_set = RepitchedWrapper(train_set, vocals=vocals, **args.augment.repitch)

    logger.info("train/valid set size: %d %d", len(train_set), len(valid_set))
    train_loader = distrib.loader(
        train_set, batch_size=args.batch_size, shuffle=True,
        num_workers=args.misc.num_workers, drop_last=True)
    if args.dset.full_cv:
        valid_loader = distrib.loader(
            valid_set, batch_size=1, shuffle=False,
            num_workers=args.misc.num_workers)
    else:
        valid_loader = distrib.loader(
            valid_set, batch_size=args.batch_size, shuffle=False,
            num_workers=args.misc.num_workers, drop_last=True)
    loaders = {"train": train_loader, "valid": valid_loader}

    # Construct Solver
    return Solver(loaders, model, optimizer, args)


def get_solver_from_sig(sig, model_only=False):
    inst = GlobalHydra.instance()
    hyd = None
    if inst.is_initialized():
        hyd = inst.hydra
        inst.clear()
    xp = main.get_xp_from_sig(sig)
    if hyd is not None:
        inst.clear()
        inst.initialize(hyd)

    with xp.enter(stack=True):
        return get_solver(xp.cfg, model_only)


@hydra_main(config_path="../conf", config_name="config", version_base="1.1")
def main(args):
    global __file__
    __file__ = hydra.utils.to_absolute_path(__file__)
    for attr in ["musdb", "wav", "metadata"]:
        val = getattr(args.dset, attr)
        if val is not None:
            setattr(args.dset, attr, hydra.utils.to_absolute_path(val))

    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"

    if args.misc.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("For logs, checkpoints and samples check %s", os.getcwd())
    logger.debug(args)
    from dora import get_xp
    logger.debug(get_xp().cfg)

    solver = get_solver(args)
    solver.train()


if '_DORA_TEST_PATH' in os.environ:
    main.dora.dir = Path(os.environ['_DORA_TEST_PATH'])


if __name__ == "__main__":
    main()
