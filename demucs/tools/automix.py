# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
This script creates realistic mixes with stems from different songs.
In particular, it will align BPM, sync up the first beat and perform pitch
shift to maximize pitches overlap.
In order to limit artifacts, only parts that can be mixed with less than 15%
tempo shift, and 3 semitones of pitch shift are mixed together.
"""
from collections import namedtuple
from concurrent.futures import ProcessPoolExecutor
import hashlib
from pathlib import Path
import random
import shutil
import tqdm
import pickle

from librosa.beat import beat_track
from librosa.feature import chroma_cqt
import numpy as np
import torch
from torch.nn import functional as F

from dora.utils import try_load
from demucs.audio import save_audio
from demucs.repitch import repitch
from demucs.pretrained import SOURCES
from demucs.wav import build_metadata, Wavset, _get_musdb_valid


MUSDB_PATH = '/checkpoint/defossez/datasets/musdbhq'
EXTRA_WAV_PATH = "/checkpoint/defossez/datasets/allstems_44"
# WARNING: OUTPATH will be completely erased.
OUTPATH = Path.home() / 'tmp/demucs_mdx/automix_musdb/'
CACHE = Path.home() / 'tmp/automix_cache'  # cache BPM and pitch information.
CHANNELS = 2
SR = 44100
MAX_PITCH = 3  # maximum allowable pitch shift in semi tones
MAX_TEMPO = 0.15  # maximum allowable tempo shift


Spec = namedtuple("Spec", "tempo onsets kr track index")


def rms(wav, window=10000):
    """efficient rms computed for each time step over a given window."""
    half = window // 2
    window = 2 * half + 1
    wav = F.pad(wav, (half, half))
    tot = wav.pow(2).cumsum(dim=-1)
    return ((tot[..., window - 1:] - tot[..., :-window + 1]) / window).sqrt()


def analyse_track(dset, index):
    """analyse track, extract bpm and distribution of notes from the bass line."""
    track = dset[index]
    mix = track.sum(0).mean(0)
    ref = mix.std()

    starts = (abs(mix) >= 1e-2 * ref).float().argmax().item()
    track = track[..., starts:]

    cache = CACHE / dset.sig
    cache.mkdir(exist_ok=True, parents=True)

    cache_file = cache / f"{index}.pkl"
    cached = None
    if cache_file.exists():
        cached = try_load(cache_file)
        if cached is not None:
            tempo, events, hist_kr = cached

    if cached is None:
        drums = track[0].mean(0)
        if drums.std() > 1e-2 * ref:
            tempo, events = beat_track(y=drums.numpy(), units='time', sr=SR)
        else:
            print("failed drums", drums.std(), ref)
            return None, track

        bass = track[1].mean(0)
        r = rms(bass)
        peak = r.max()
        mask = r >= 0.05 * peak
        bass = bass[mask]
        if bass.std() > 1e-2 * ref:
            kr = torch.from_numpy(chroma_cqt(y=bass.numpy(), sr=SR))
            hist_kr = (kr.max(dim=0, keepdim=True)[0] == kr).float().mean(1)
        else:
            print("failed bass", bass.std(), ref)
            return None, track

    pickle.dump([tempo, events, hist_kr], open(cache_file, 'wb'))
    spec = Spec(tempo, events, hist_kr, track, index)
    return spec, None


def best_pitch_shift(kr_a, kr_b):
    """find the best pitch shift between two chroma distributions."""
    deltas = []
    for p in range(12):
        deltas.append((kr_a - kr_b).abs().mean())
        kr_b = kr_b.roll(1, 0)

    ps = np.argmin(deltas)
    if ps > 6:
        ps = ps - 12
    return ps


def align_stems(stems):
    """Align the first beats of the stems.
    This is a naive implementation. A grid with a time definition 10ms is defined and
    each beat onset is represented as a gaussian over this grid.
    Then, we try each possible time shift to make two grids align the best.
    We repeat for all sources.
    """
    sources = len(stems)
    width = 5e-3  # grid of 10ms
    limit = 5
    std = 2
    x = torch.arange(-limit, limit + 1, 1).float()
    gauss = torch.exp(-x**2 / (2 * std**2))

    grids = []
    for wav, onsets in stems:
        le = wav.shape[-1]
        dur = le / SR
        grid = torch.zeros(int(le / width / SR))
        for onset in onsets:
            pos = int(onset / width)
            if onset >= dur - 1:
                continue
            if onset < 1:
                continue
            grid[pos - limit:pos + limit + 1] += gauss
        grids.append(grid)

    shifts = [0]
    for s in range(1, sources):
        max_shift = int(4 / width)
        dots = []
        for shift in range(-max_shift, max_shift):
            other = grids[s]
            ref = grids[0]
            if shift >= 0:
                other = other[shift:]
            else:
                ref = ref[shift:]
            le = min(len(other), len(ref))
            dots.append((ref[:le].dot(other[:le]), int(shift * width * SR)))

        _, shift = max(dots)
        shifts.append(-shift)

    outs = []
    new_zero = min(shifts)
    for (wav, _), shift in zip(stems, shifts):
        offset = shift - new_zero
        wav = F.pad(wav, (offset, 0))
        outs.append(wav)

    le = min(x.shape[-1] for x in outs)

    outs = [w[..., :le] for w in outs]
    return torch.stack(outs)


def find_candidate(spec_ref, catalog, pitch_match=True):
    """Given reference track, this finds a track in the catalog that
    is a potential match (pitch and tempo delta must be within the allowable limits).
    """
    candidates = list(catalog)
    random.shuffle(candidates)

    for spec in candidates:
        ok = False
        for scale in [1/4, 1/2, 1, 2, 4]:
            tempo = spec.tempo * scale
            delta_tempo = spec_ref.tempo / tempo - 1
            if abs(delta_tempo) < MAX_TEMPO:
                ok = True
                break
        if not ok:
            print(delta_tempo, spec_ref.tempo, spec.tempo, "FAILED TEMPO")
            # too much of a tempo difference
            continue
        spec = spec._replace(tempo=tempo)

        ps = 0
        if pitch_match:
            ps = best_pitch_shift(spec_ref.kr, spec.kr)
            if abs(ps) > MAX_PITCH:
                print("Failed pitch", ps)
                # too much pitch difference
                continue
        return spec, delta_tempo, ps


def get_part(spec, source, dt, dp):
    """Apply given delta of tempo and delta of pitch to a stem."""
    wav = spec.track[source]
    if dt or dp:
        wav = repitch(wav, dp, dt * 100, samplerate=SR, voice=source == 3)
        spec = spec._replace(onsets=spec.onsets / (1 + dt))
    return wav, spec


def build_track(ref_index, catalog):
    """Given the reference track index and a catalog of track, builds
    a completely new track. One of the source at random from the ref track will
    be kept and other sources will be drawn from the catalog.
    """
    order = list(range(len(SOURCES)))
    random.shuffle(order)

    stems = [None] * len(order)
    indexes = [None] * len(order)
    origs = [None] * len(order)
    dps = [None] * len(order)
    dts = [None] * len(order)

    first = order[0]
    spec_ref = catalog[ref_index]
    stems[first] = (spec_ref.track[first], spec_ref.onsets)
    indexes[first] = ref_index
    origs[first] = spec_ref.track[first]
    dps[first] = 0
    dts[first] = 0

    pitch_match = order != 0

    for src in order[1:]:
        spec, dt, dp = find_candidate(spec_ref, catalog, pitch_match=pitch_match)
        if not pitch_match:
            spec_ref = spec_ref._replace(kr=spec.kr)
        pitch_match = True
        dps[src] = dp
        dts[src] = dt
        wav, spec = get_part(spec, src, dt, dp)
        stems[src] = (wav, spec.onsets)
        indexes[src] = spec.index
        origs.append(spec.track[src])
    print("FINAL CHOICES", ref_index, indexes, dps, dts)
    stems = align_stems(stems)
    return stems, origs


def get_musdb_dataset(part='train'):
    root = Path(MUSDB_PATH) / part
    ext = '.wav'
    metadata = build_metadata(root, SOURCES, ext=ext, normalize=False)
    valid_tracks = _get_musdb_valid()
    metadata_train = {name: meta for name, meta in metadata.items() if name not in valid_tracks}
    train_set = Wavset(
        root, metadata_train, SOURCES, samplerate=SR, channels=CHANNELS,
        normalize=False, ext=ext)
    sig = hashlib.sha1(str(root).encode()).hexdigest()[:8]
    train_set.sig = sig
    return train_set


def get_wav_dataset():
    root = Path(EXTRA_WAV_PATH)
    ext = '.wav'
    metadata = _build_metadata(root, SOURCES, ext=ext, normalize=False)
    train_set = Wavset(
        root, metadata, SOURCES, samplerate=SR, channels=CHANNELS,
        normalize=False, ext=ext)
    sig = hashlib.sha1(str(root).encode()).hexdigest()[:8]
    train_set.sig = sig
    return train_set


def main():
    random.seed(4321)
    if OUTPATH.exists():
        shutil.rmtree(OUTPATH)
    OUTPATH.mkdir(exist_ok=True, parents=True)
    (OUTPATH / 'train').mkdir(exist_ok=True, parents=True)
    (OUTPATH / 'valid').mkdir(exist_ok=True, parents=True)
    out = OUTPATH / 'train'

    dset = get_musdb_dataset()
    # dset2 = get_wav_dataset()
    # dset3 = get_musdb_dataset('test')
    dset2 = None
    dset3 = None
    pendings = []
    copies = 6
    copies_rej = 2

    with ProcessPoolExecutor(20) as pool:
        for index in range(len(dset)):
            pendings.append(pool.submit(analyse_track, dset, index))

        if dset2:
            for index in range(len(dset2)):
                pendings.append(pool.submit(analyse_track, dset2, index))
        if dset3:
            for index in range(len(dset3)):
                pendings.append(pool.submit(analyse_track, dset3, index))

        catalog = []
        rej = 0
        for pending in tqdm.tqdm(pendings, ncols=120):
            spec, track = pending.result()
            if spec is not None:
                catalog.append(spec)
            else:
                mix = track.sum(0)
                for copy in range(copies_rej):
                    folder = out / f'rej_{rej}_{copy}'
                    folder.mkdir()
                    save_audio(mix, folder / "mixture.wav", SR)
                    for stem, source in zip(track, SOURCES):
                        save_audio(stem, folder / f"{source}.wav", SR, clip='clamp')
                    rej += 1

    for copy in range(copies):
        for index in range(len(catalog)):
            track, origs = build_track(index, catalog)
            mix = track.sum(0)
            mx = mix.abs().max()
            scale = max(1, 1.01 * mx)
            mix = mix / scale
            track = track / scale
            folder = out / f'{copy}_{index}'
            folder.mkdir()
            save_audio(mix, folder / "mixture.wav", SR)
            for stem, source, orig in zip(track, SOURCES, origs):
                save_audio(stem, folder / f"{source}.wav", SR, clip='clamp')
                # save_audio(stem.std() * orig / (1e-6 + orig.std()), folder / f"{source}_orig.wav",
                #            SR, clip='clamp')


if __name__ == '__main__':
    main()
