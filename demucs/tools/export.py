# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Export a trained model from the full checkpoint (with optimizer etc.) to
a final checkpoint, with only the model itself. The model is always stored as
half float to gain space, and because this has zero impact on the final loss.
When DiffQ was used for training, the model will actually be quantized and bitpacked."""
from argparse import ArgumentParser
from fractions import Fraction
import logging
from pathlib import Path
import sys
import torch

from demucs import train
from demucs.states import serialize_model, save_with_checksum


logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    parser = ArgumentParser("tools.export", description="Export trained models from XP sigs.")
    parser.add_argument('signatures', nargs='*', help='XP signatures.')
    parser.add_argument('-o', '--out', type=Path, default=Path("release_models"),
                        help="Path where to store release models (default release_models)")
    parser.add_argument('-s', '--sign', action='store_true',
                        help='Add sha256 prefix checksum to the filename.')

    args = parser.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)

    for sig in args.signatures:
        xp = train.main.get_xp_from_sig(sig)
        name = train.main.get_name(xp)
        logger.info('Handling %s/%s', sig, name)

        out_path = args.out / (sig + ".th")

        solver = train.get_solver_from_sig(sig)
        if len(solver.history) < solver.args.epochs:
            logger.warning(
                'Model %s has less epoch than expected (%d / %d)',
                sig, len(solver.history), solver.args.epochs)

        solver.model.load_state_dict(solver.best_state)
        pkg = serialize_model(solver.model, solver.args, solver.quantizer, half=True)
        if getattr(solver.model, 'use_train_segment', False):
            batch = solver.augment(next(iter(solver.loaders['train'])))
            pkg['kwargs']['segment'] = Fraction(batch.shape[-1], solver.model.samplerate)
            print("Override", pkg['kwargs']['segment'])
        valid, test = None, None
        for m in solver.history:
            if 'valid' in m:
                valid = m['valid']
            if 'test' in m:
                test = m['test']
        pkg['metrics'] = (valid, test)
        if args.sign:
            save_with_checksum(pkg, out_path)
        else:
            torch.save(pkg, out_path)


if __name__ == '__main__':
    main()
