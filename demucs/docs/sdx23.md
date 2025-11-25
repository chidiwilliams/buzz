# SDX 23 challenge

Checkout [the challenge page](https://www.aicrowd.com/challenges/sound-demixing-challenge-2023)
for more information. This page is specifically on training models for the [MDX'23 sub-challenge](https://www.aicrowd.com/challenges/sound-demixing-challenge-2023/problems/music-demixing-track-mdx-23).
There are two tracks: one trained on a dataset with bleeding, and the other with label mixups.

This gives instructions on training an Hybrid Demucs model on those datasets.
I haven't tried the HT Demucs model, as it typically requires quite a bit of training data but the same could be done with it.

You will need to work from an up to date clone of this repo. See the [generic training instructions](./training.md) for more information.

## Getting the data

Register on the challenge, then checkout the [Resources page](https://www.aicrowd.com/challenges/sound-demixing-challenge-2023/problems/music-demixing-track-mdx-23/dataset_files) and download the dataset you are
interested in.

Update the `conf/dset/sdx23_bleeding.yaml` and `conf/dset/sdx23_labelnoise.yaml` files to point to the right path.

**Make sure soundfile** is installed (`conda install -c conda-forge libsndfile; pip install soundfile`).

### Create proper train / valid structure

Demucs requires a valid set to work properly. Go to the folder where you extracted the tracks then do:

```shell
mkdir train
mv * train    # there will be a warning saying cannot move train to itself but  that's fine the other tracks should have.
mkdir valid
cd train
mv 5640831d-7853-4d06-8166-988e2844b652  bc964128-da16-4e4c-af95-4d1211e78c70 \
	cc7f7675-d3c8-4a49-a2d7-a8959b694004  f40ffd10-4e8b-41e6-bd8a-971929ca9138 \
	bc1f2967-f834-43bd-aadc-95afc897cfe7  cc3e4991-6cce-40fe-a917-81a4fbb92ea6  \
	ed90a89a-bf22-444d-af3d-d9ac3896ebd2  f4b735de-14b1-4091-a9ba-c8b30c0740a7 ../valid
```

## Training

See `dora grid sdx23` for a starting point. You can do `dora grid sdx23 --init --dry_run` then `dora run -f SIG -d` with `SIG` one of the signature
to train on a machine with GPUs if you do not have a SLURM cluster.

Keep in mind that the valid tracks and train tracks are corrupted in different ways for those tasks, so do not expect
the valid loss to go down as smoothly as with normal training on the clean MusDB.

I only trained Hybrid Demucs baselines as Hybrid Transformer typically requires more data.


## Exporting models

Run
```
python -m tools.export SIG
```

This will export the trained model into the `release_models` folder.

## Submitting a model

Clone the [Demucs Starter Kit for SDX23](https://github.com/adefossez/sdx23). Follow the instructions there.

You will to copy the models under `release_models` in the `sdx23/models/` folder before you can use them.
Make sure you have git-lfs properly installed and setup before adding those files to your fork of `sdx23`.
