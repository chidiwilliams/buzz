# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
benchmarking script, useful to check for OOM, reasonable train time,
and for the MDX competion, estimate if we will match the time limit."""
from contextlib import contextmanager
import logging
import sys
import time
import torch

from demucs.train import get_solver, main
from demucs.apply import apply_model

logging.basicConfig(level=logging.INFO, stream=sys.stderr)


class Result:
    pass


@contextmanager
def bench():
    import gc
    gc.collect()
    torch.cuda.reset_max_memory_allocated()
    torch.cuda.empty_cache()
    result = Result()
    # before = torch.cuda.memory_allocated()
    before = 0
    begin = time.time()
    try:
        yield result
    finally:
        torch.cuda.synchronize()
        mem = (torch.cuda.max_memory_allocated() - before) / 2 ** 20
        tim = time.time() - begin
        result.mem = mem
        result.tim = tim


xp = main.get_xp_from_sig(sys.argv[1])
xp = main.get_xp(xp.argv + sys.argv[2:])
with xp.enter():
    solver = get_solver(xp.cfg)
    if getattr(solver.model, 'use_train_segment', False):
        batch = solver.augment(next(iter(solver.loaders['train'])))
        solver.model.segment = Fraction(batch.shape[-1], solver.model.samplerate)
        train_segment = solver.model.segment
        solver.model.eval()
    model = solver.model
    model.cuda()
    x = torch.randn(2, xp.cfg.dset.channels, int(10 * model.samplerate), device='cuda')
    with bench() as res:
        y = model(x)
        y.sum().backward()
    del y
    for p in model.parameters():
        p.grad = None
    print(f"FB: {res.mem:.1f} MB, {res.tim * 1000:.1f} ms")

    x = torch.randn(1, xp.cfg.dset.channels, int(model.segment * model.samplerate), device='cuda')
    with bench() as res:
        with torch.no_grad():
            y = model(x)
    del y
    print(f"FV: {res.mem:.1f} MB, {res.tim * 1000:.1f} ms")

    model.cpu()
    torch.set_num_threads(1)
    test = torch.randn(1, xp.cfg.dset.channels, model.samplerate * 40)
    b = time.time()
    apply_model(model, test, split=True, shifts=1)
    print("CPU 40 sec:", time.time() - b)
