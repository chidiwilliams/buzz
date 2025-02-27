# Release notes for Demucs

## V4.1.0a, TBD

Get models list

Check segment of HTDemucs inside BagOfModels

Added api.py to be called from another program

Use api in separate.py

Added `--other-method`: method to get `no_{STEM}`, add up all the other stems (add), original track substract the specific stem (minus), and discard (none)

Added type `HTDemucs` to type alias `AnyModel`.

Improving recent torchaudio versions support (Thanks @CarlGao4) 

## V4.0.1, 8th of September 2023

**From this version, Python 3.7 is no longer supported. This is not a problem since the latest PyTorch 2.0.0 no longer support it either.**

Various improvements by @CarlGao4. Support for `segment` param inside of HTDemucs
model.

Made diffq an optional dependency, with an error message if not installed.

Added output format flac (Free Lossless Audio Codec)

Will use CPU for complex numbers, when using MPS device (all other computations are performed by mps).

Optimize codes to save memory

Allow changing preset of MP3

## V4.0.0, 7th of December 2022

Adding hybrid transformer Demucs model.

Added support for [Torchaudio implementation of HDemucs](https://pytorch.org/audio/main/tutorials/hybrid_demucs_tutorial.html), thanks @skim0514.

Added experimental 6 sources model `htdemucs_6s` (`drums`, `bass`, `other`, `vocals`, `piano`, `guitar`).

## V3.0.6, 16th of November 2022

Option to customize output path of stems (@CarlGao4)

Fixed bug in pad1d leading to failure sometimes.

## V3.0.5, 17th of August 2022

Added `--segment` flag to customize the segment length and use less memory (thanks @CarlGao4).

Fix reflect padding bug on small inputs.

Compatible with pyTorch 1.12

## V3.0.4, 24th of February 2022

Added option to split into two stems (i.e. vocals, vs. non vocals), thanks to @CarlGao4.

Added `--float32`, `--int24` and `--clip-mode` options to customize how output stems are saved.

## V3.0.3, 2nd of December 2021

Fix bug in weights used for different sources. Thanks @keunwoochoi for the report and fix.

Improving drastically memory usage on GPU for long files. Thanks a lot @famzah for providing this.

Adding multithread evaluation on CPU (`-j` option).

(v3.0.2 had a bug with the CPU pool and is skipped.)

## V3.0.1, 12th of November 2021

Release of Demucs v3, featuring hybrid domain separation and much more.
This drops support for Conv-Tasnet and training on the non HQ MusDB dataset.
There is no version 3.0.0 because I messed up.

## V2.0.2, 26th of May 2021

- Fix in Tasnet (PR #178)
- Use ffmpeg in priority when available instead of torchaudio to avoid small shift in MP3 data.
- other minor fixes

## v2.0.1, 11th of May 2021

MusDB HQ support added. Custom wav dataset support added.
Minor changes: issue with padding of mp3 and torchaudio reading, in order to limit that,
Demucs now uses ffmpeg in priority and fallback to torchaudio.
Replaced pre-trained demucs model with one trained on more recent codebase.

## v2.0.0, 28th of April 2021

This is a big release, with at lof of breaking changes. You will likely
need to install Demucs from scratch.



- Demucs now supports on the fly resampling by a factor of 2.
This improves SDR almost 0.3 points.
- Random scaling of each source added (From Uhlich et al. 2017).
- Random pitch and tempo augmentation addded, from [Cohen-Hadria et al. 2019].
- With extra augmentation, the best performing Demucs model now has only 64 channels
instead of 100, so model size goes from 2.4GB to 1GB. Also SDR is up from 5.6 SDR to 6.3 when trained only on MusDB.
-  Quantized model using [DiffQ](https://github.com/facebookresearch/diffq) has been added. Model size is 150MB, no loss in quality as far as I, or the metrics,
can say.
- Pretrained models are now using the TorchHub interface.
- Overlap mode for separation, to limit inconsitencies at
	frame boundaries, with linear transition over the overlap. Overlap is currently
	at 25%. Not that this is only done for separation, not training, because
	I added that quite late to the code. For Conv-TasNet this can improve
	SDR quite a bit (+0.3 points, to 6.0).
- PyPI hosting, for separation, not training!
