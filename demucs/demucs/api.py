# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""API methods for demucs

Classes
-------
`demucs.api.Separator`: The base separator class

Functions
---------
`demucs.api.save_audio`: Save an audio
`demucs.api.list_models`: Get models list

Examples
--------
See the end of this module (if __name__ == "__main__")
"""

import subprocess

from . import audio_legacy
import torch as th
import torchaudio as ta

from dora.log import fatal
from pathlib import Path
from typing import Optional, Callable, Dict, Tuple, Union

from .apply import apply_model, _replace_dict
from .audio import AudioFile, convert_audio, save_audio
from .pretrained import get_model, _parse_remote_files, REMOTE_ROOT
from .repo import RemoteRepo, LocalRepo, ModelOnlyRepo, BagOnlyRepo


class LoadAudioError(Exception):
    pass


class LoadModelError(Exception):
    pass


class _NotProvided:
    pass


NotProvided = _NotProvided()


class Separator:
    def __init__(
        self,
        model: str = "htdemucs",
        repo: Optional[Path] = None,
        device: str = "cuda" if th.cuda.is_available() else "cpu",
        shifts: int = 1,
        overlap: float = 0.25,
        split: bool = True,
        segment: Optional[int] = None,
        jobs: int = 0,
        progress: bool = False,
        callback: Optional[Callable[[dict], None]] = None,
        callback_arg: Optional[dict] = None,
    ):
        """
        `class Separator`
        =================

        Parameters
        ----------
        model: Pretrained model name or signature. Default is htdemucs.
        repo: Folder containing all pre-trained models for use.
        segment: Length (in seconds) of each segment (only available if `split` is `True`). If \
            not specified, will use the command line option.
        shifts: If > 0, will shift in time `wav` by a random amount between 0 and 0.5 sec and \
            apply the oppositve shift to the output. This is repeated `shifts` time and all \
            predictions are averaged. This effectively makes the model time equivariant and \
            improves SDR by up to 0.2 points. If not specified, will use the command line option.
        split: If True, the input will be broken down into small chunks (length set by `segment`) \
            and predictions will be performed individually on each and concatenated. Useful for \
            model with large memory footprint like Tasnet. If not specified, will use the command \
            line option.
        overlap: The overlap between the splits. If not specified, will use the command line \
            option.
        device (torch.device, str, or None): If provided, device on which to execute the \
            computation, otherwise `wav.device` is assumed. When `device` is different from \
            `wav.device`, only local computations will be on `device`, while the entire tracks \
            will be stored on `wav.device`. If not specified, will use the command line option.
        jobs: Number of jobs. This can increase memory usage but will be much faster when \
            multiple cores are available. If not specified, will use the command line option.
        callback: A function will be called when the separation of a chunk starts or finished. \
            The argument passed to the function will be a dict. For more information, please see \
            the Callback section.
        callback_arg: A dict containing private parameters to be passed to callback function. For \
            more information, please see the Callback section.
        progress: If true, show a progress bar.

        Callback
        --------
        The function will be called with only one positional parameter whose type is `dict`. The
        `callback_arg` will be combined with information of current separation progress. The
        progress information will override the values in `callback_arg` if same key has been used.
        To abort the separation, raise `KeyboardInterrupt`.

        Progress information contains several keys (These keys will always exist):
        - `model_idx_in_bag`: The index of the submodel in `BagOfModels`. Starts from 0.
        - `shift_idx`: The index of shifts. Starts from 0.
        - `segment_offset`: The offset of current segment. If the number is 441000, it doesn't
            mean that it is at the 441000 second of the audio, but the "frame" of the tensor.
        - `state`: Could be `"start"` or `"end"`.
        - `audio_length`: Length of the audio (in "frame" of the tensor).
        - `models`: Count of submodels in the model.
        """
        self._name = model
        self._repo = repo
        self._load_model()
        self.update_parameter(device=device, shifts=shifts, overlap=overlap, split=split,
                              segment=segment, jobs=jobs, progress=progress, callback=callback,
                              callback_arg=callback_arg)

    def update_parameter(
        self,
        device: Union[str, _NotProvided] = NotProvided,
        shifts: Union[int, _NotProvided] = NotProvided,
        overlap: Union[float, _NotProvided] = NotProvided,
        split: Union[bool, _NotProvided] = NotProvided,
        segment: Optional[Union[int, _NotProvided]] = NotProvided,
        jobs: Union[int, _NotProvided] = NotProvided,
        progress: Union[bool, _NotProvided] = NotProvided,
        callback: Optional[
            Union[Callable[[dict], None], _NotProvided]
        ] = NotProvided,
        callback_arg: Optional[Union[dict, _NotProvided]] = NotProvided,
    ):
        """
        Update the parameters of separation.

        Parameters
        ----------
        segment: Length (in seconds) of each segment (only available if `split` is `True`). If \
            not specified, will use the command line option.
        shifts: If > 0, will shift in time `wav` by a random amount between 0 and 0.5 sec and \
            apply the oppositve shift to the output. This is repeated `shifts` time and all \
            predictions are averaged. This effectively makes the model time equivariant and \
            improves SDR by up to 0.2 points. If not specified, will use the command line option.
        split: If True, the input will be broken down into small chunks (length set by `segment`) \
            and predictions will be performed individually on each and concatenated. Useful for \
            model with large memory footprint like Tasnet. If not specified, will use the command \
            line option.
        overlap: The overlap between the splits. If not specified, will use the command line \
            option.
        device (torch.device, str, or None): If provided, device on which to execute the \
            computation, otherwise `wav.device` is assumed. When `device` is different from \
            `wav.device`, only local computations will be on `device`, while the entire tracks \
            will be stored on `wav.device`. If not specified, will use the command line option.
        jobs: Number of jobs. This can increase memory usage but will be much faster when \
            multiple cores are available. If not specified, will use the command line option.
        callback: A function will be called when the separation of a chunk starts or finished. \
            The argument passed to the function will be a dict. For more information, please see \
            the Callback section.
        callback_arg: A dict containing private parameters to be passed to callback function. For \
            more information, please see the Callback section.
        progress: If true, show a progress bar.

        Callback
        --------
        The function will be called with only one positional parameter whose type is `dict`. The
        `callback_arg` will be combined with information of current separation progress. The
        progress information will override the values in `callback_arg` if same key has been used.
        To abort the separation, raise `KeyboardInterrupt`.

        Progress information contains several keys (These keys will always exist):
        - `model_idx_in_bag`: The index of the submodel in `BagOfModels`. Starts from 0.
        - `shift_idx`: The index of shifts. Starts from 0.
        - `segment_offset`: The offset of current segment. If the number is 441000, it doesn't
            mean that it is at the 441000 second of the audio, but the "frame" of the tensor.
        - `state`: Could be `"start"` or `"end"`.
        - `audio_length`: Length of the audio (in "frame" of the tensor).
        - `models`: Count of submodels in the model.
        """
        if not isinstance(device, _NotProvided):
            self._device = device
        if not isinstance(shifts, _NotProvided):
            self._shifts = shifts
        if not isinstance(overlap, _NotProvided):
            self._overlap = overlap
        if not isinstance(split, _NotProvided):
            self._split = split
        if not isinstance(segment, _NotProvided):
            self._segment = segment
        if not isinstance(jobs, _NotProvided):
            self._jobs = jobs
        if not isinstance(progress, _NotProvided):
            self._progress = progress
        if not isinstance(callback, _NotProvided):
            self._callback = callback
        if not isinstance(callback_arg, _NotProvided):
            self._callback_arg = callback_arg

    def _load_model(self):
        self._model = get_model(name=self._name, repo=self._repo)
        if self._model is None:
            raise LoadModelError("Failed to load model")
        self._audio_channels = self._model.audio_channels
        self._samplerate = self._model.samplerate

    def _load_audio(self, track: Path):
        errors = {}
        wav = None

        try:
            wav = AudioFile(track).read(streams=0, samplerate=self._samplerate,
                                        channels=self._audio_channels)
        except FileNotFoundError:
            errors["ffmpeg"] = "FFmpeg is not installed."
        except subprocess.CalledProcessError:
            errors["ffmpeg"] = "FFmpeg could not read the file."

        if wav is None:
            try:
                wav, sr = ta.load(str(track))
            except RuntimeError as err:
                errors["torchaudio"] = err.args[0]
            else:
                wav = convert_audio(wav, sr, self._samplerate, self._audio_channels)

        if wav is None:
            raise LoadAudioError(
                "\n".join(
                    "When trying to load using {}, got the following error: {}".format(
                        backend, error
                    )
                    for backend, error in errors.items()
                )
            )
        return wav

    def separate_tensor(
        self, wav: th.Tensor, sr: Optional[int] = None
    ) -> Tuple[th.Tensor, Dict[str, th.Tensor]]:
        """
        Separate a loaded tensor.

        Parameters
        ----------
        wav: Waveform of the audio. Should have 2 dimensions, the first is each audio channel, \
            while the second is the waveform of each channel. Type should be float32. \
            e.g. `tuple(wav.shape) == (2, 884000)` means the audio has 2 channels.
        sr: Sample rate of the original audio, the wave will be resampled if it doesn't match the \
            model.

        Returns
        -------
        A tuple, whose first element is the original wave and second element is a dict, whose keys
        are the name of stems and values are separated waves. The original wave will have already
        been resampled.

        Notes
        -----
        Use this function with cautiousness. This function does not provide data verifying.
        """
        if sr is not None and sr != self.samplerate:
            wav = convert_audio(wav, sr, self._samplerate, self._audio_channels)
        ref = wav.mean(0)
        wav -= ref.mean()
        wav /= ref.std() + 1e-8
        out = apply_model(
                self._model,
                wav[None],
                segment=self._segment,
                shifts=self._shifts,
                split=self._split,
                overlap=self._overlap,
                device=self._device,
                num_workers=self._jobs,
                callback=self._callback,
                callback_arg=_replace_dict(
                    self._callback_arg, ("audio_length", wav.shape[1])
                ),
                progress=self._progress,
            )
        if out is None:
            raise KeyboardInterrupt
        out *= ref.std() + 1e-8
        out += ref.mean()
        wav *= ref.std() + 1e-8
        wav += ref.mean()
        return (wav, dict(zip(self._model.sources, out[0])))

    def separate_audio_file(self, file: Path):
        """
        Separate an audio file. The method will automatically read the file.

        Parameters
        ----------
        wav: Path of the file to be separated.

        Returns
        -------
        A tuple, whose first element is the original wave and second element is a dict, whose keys
        are the name of stems and values are separated waves. The original wave will have already
        been resampled.
        """
        return self.separate_tensor(self._load_audio(file), self.samplerate)

    @property
    def samplerate(self):
        return self._samplerate

    @property
    def audio_channels(self):
        return self._audio_channels

    @property
    def model(self):
        return self._model


def list_models(repo: Optional[Path] = None) -> Dict[str, Dict[str, Union[str, Path]]]:
    """
    List the available models. Please remember that not all the returned models can be
    successfully loaded.

    Parameters
    ----------
    repo: The repo whose models are to be listed.

    Returns
    -------
    A dict with two keys ("single" for single models and "bag" for bag of models). The values are
    lists whose components are strs.
    """
    model_repo: ModelOnlyRepo
    if repo is None:
        models = _parse_remote_files(REMOTE_ROOT / 'files.txt')
        model_repo = RemoteRepo(models)
        bag_repo = BagOnlyRepo(REMOTE_ROOT, model_repo)
    else:
        if not repo.is_dir():
            fatal(f"{repo} must exist and be a directory.")
        model_repo = LocalRepo(repo)
        bag_repo = BagOnlyRepo(repo, model_repo)
    return {"single": model_repo.list_model(), "bag": bag_repo.list_model()}


if __name__ == "__main__":
    # Test API functions
    # two-stem not supported

    from .separate import get_parser

    args = get_parser().parse_args()
    separator = Separator(
        model=args.name,
        repo=args.repo,
        device=args.device,
        shifts=args.shifts,
        overlap=args.overlap,
        split=args.split,
        segment=args.segment,
        jobs=args.jobs,
        callback=print
    )
    out = args.out / args.name
    out.mkdir(parents=True, exist_ok=True)
    for file in args.tracks:
        separated = separator.separate_audio_file(file)[1]
        if args.mp3:
            ext = "mp3"
        elif args.flac:
            ext = "flac"
        else:
            ext = "wav"
        kwargs = {
            "samplerate": separator.samplerate,
            "bitrate": args.mp3_bitrate,
            "clip": args.clip_mode,
            "as_float": args.float32,
            "bits_per_sample": 24 if args.int24 else 16,
        }
        for stem, source in separated.items():
            stem = out / args.filename.format(
                track=Path(file).name.rsplit(".", 1)[0],
                trackext=Path(file).name.rsplit(".", 1)[-1],
                stem=stem,
                ext=ext,
            )
            stem.parent.mkdir(parents=True, exist_ok=True)
            save_audio(source, str(stem), **kwargs)
