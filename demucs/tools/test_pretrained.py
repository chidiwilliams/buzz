# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# Script to evaluate pretrained models.

from argparse import ArgumentParser
import logging
import sys

import torch

from demucs import train, pretrained, evaluate


def main():
    torch.set_num_threads(1)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    parser = ArgumentParser("tools.test_pretrained",
                            description="Evaluate pre-trained models or bags of models "
                                        "on MusDB.")
    pretrained.add_model_flags(parser)
    parser.add_argument('overrides', nargs='*',
                        help='Extra overrides, e.g. test.shifts=2.')
    args = parser.parse_args()

    xp = train.main.get_xp(args.overrides)
    with xp.enter():
        solver = train.get_solver(xp.cfg)

    model = pretrained.get_model_from_args(args)
    solver.model = model.to(solver.device)
    solver.model.eval()

    with torch.no_grad():
        results = evaluate.evaluate(solver, xp.cfg.test.sdr)
    print(results)


if __name__ == '__main__':
    main()
