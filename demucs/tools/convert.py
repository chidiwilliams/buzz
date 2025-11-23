# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# Script to convert option names and model args from the dev branch to
# the cleanup release one. There should be no reaso to use that anymore.

import argparse
import io
import json
from pathlib import Path
import subprocess as sp

import torch

from demucs import train, pretrained, states

DEV_REPO = Path.home() / 'tmp/release_demucs_mdx'


TO_REMOVE = [
    'demucs.dconv_kw.gelu=True',
    'demucs.dconv_kw.nfreqs=0',
    'demucs.dconv_kw.nfreqs=0',
    'demucs.dconv_kw.version=4',
    'demucs.norm=gn',
    'wdemucs.nice=True',
    'wdemucs.good=True',
    'wdemucs.freq_emb=-0.2',
    'special=True',
    'special=False',
]

TO_REPLACE = [
    ('power', 'svd'),
    ('wdemucs', 'hdemucs'),
    ('hdemucs.hybrid=True', 'hdemucs.hybrid_old=True'),
    ('hdemucs.hybrid=2', 'hdemucs.hybrid=True'),
]

TO_INJECT = [
    ('model=hdemucs', ['hdemucs.cac=False']),
    ('model=hdemucs', ['hdemucs.norm_starts=999']),
]


def get_original_argv(sig):
    return json.load(open(Path(DEV_REPO) / f'outputs/xps/{sig}/.argv.json'))


def transform(argv, mappings, verbose=False):
    for rm in TO_REMOVE:
        while rm in argv:
            argv.remove(rm)

    for old, new in TO_REPLACE:
        argv[:] = [a.replace(old, new) for a in argv]

    for condition, args in TO_INJECT:
        if condition in argv:
            argv[:] = args + argv

    for idx, arg in enumerate(argv):
        if 'continue_from=' in arg:
            dep_sig = arg.split('=')[1]
            if dep_sig.startswith('"'):
                dep_sig = eval(dep_sig)
            if verbose:
                print("Need to recursively convert dependency XP", dep_sig)
            new_sig = convert(dep_sig, mappings, verbose).sig
            argv[idx] = f'continue_from="{new_sig}"'


def convert(sig, mappings, verbose=False):
    argv = get_original_argv(sig)
    if verbose:
        print("Original argv", argv)
    transform(argv, mappings, verbose)
    if verbose:
        print("New argv", argv)
    xp = train.main.get_xp(argv)
    train.main.init_xp(xp)
    if verbose:
        print("Mapping", sig, "->", xp.sig)
    mappings[sig] = xp.sig
    return xp


def _eval_old(old_sig, x):
    script = (
        'from demucs import pretrained; import torch; import sys; import io; '
        'buf = io.BytesIO(sys.stdin.buffer.read()); '
        'x = torch.load(buf); m = pretrained.load_pretrained_model('
        f'"{old_sig}"); torch.save(m(x), sys.stdout.buffer)')

    buf = io.BytesIO()
    torch.save(x, buf)
    proc = sp.run(
        ['python3', '-c', script], input=buf.getvalue(), capture_output=True, cwd=DEV_REPO)
    if proc.returncode != 0:
        print("Error", proc.stderr.decode())
        assert False

    buf = io.BytesIO(proc.stdout)
    return torch.load(buf)


def compare(old_sig, model):
    test = torch.randn(1, 2, 44100 * 10)
    old_out = _eval_old(old_sig, test)
    out = model(test)

    delta = 20 * torch.log10((out - old_out).norm() / out.norm()).item()
    return delta


def main():
    torch.manual_seed(1234)
    parser = argparse.ArgumentParser('convert')
    parser.add_argument('sigs', nargs='*')
    parser.add_argument('-o', '--output', type=Path, default=Path('release_models'))
    parser.add_argument('-d', '--dump', action='store_true')
    parser.add_argument('-c', '--compare', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()

    args.output.mkdir(exist_ok=True, parents=True)
    mappings = {}
    for sig in args.sigs:
        xp = convert(sig, mappings, args.verbose)
        if args.dump or args.compare:
            old_pkg = pretrained._load_package(sig, old=True)
            model = train.get_model(xp.cfg)
            model.load_state_dict(old_pkg['state'])
            if args.dump:
                pkg = states.serialize_model(model, xp.cfg)
                states.save_with_checksum(pkg, args.output / f'{xp.sig}.th')
            if args.compare:
                delta = compare(sig, model)
                print("Delta for", sig, xp.sig, delta)

        mappings[sig] = xp.sig

    print("FINAL MAPPINGS")
    for old, new in mappings.items():
        print(old, " ", new)


if __name__ == '__main__':
    main()
