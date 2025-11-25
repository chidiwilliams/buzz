# Training (Hybrid) Demucs

## Install all the dependencies

You should install all the dependencies either with either Anaconda (using the env file `environment-cuda.yml` )
or `pip`, with `requirements.txt`.

## Datasets

### MusDB HQ

Note that we do not support MusDB non HQ training anymore.
Get the [Musdb HQ](https://zenodo.org/record/3338373) dataset, and update the path to it in two places:
- The `dset.musdb` key inside `conf/config.yaml`.
- The variable `MUSDB_PATH` inside `tools/automix.py`.

### Create the fine tuning datasets

**This is only for the MDX 2021 competition models**

I use a fine tuning on a dataset crafted by remixing songs in a musically plausible way.
The automix script will make sure that BPM, first beat and pitches are aligned.
In the file `tools/automix.py`, edit `OUTPATH` to suit your setup, as well as the `MUSDB_PATH`
to point to your copy of MusDB HQ. Then run

```bash
export NUMBA_NUM_THREADS=1; python3 -m tools.automix
```

**Important:** the script will show many errors, those are normals. They just indicate when two stems
 do not batch due to BPM or music scale difference.

Finally, edit the file `conf/dset/auto_mus.yaml` and replace `dset.wav` to the value of `OUTPATH`.

If you have a custom dataset, you can also uncomment the lines `dset2 = ...` and
`dset3 = ...` to add your custom wav data and the test set of MusDB for Track B models.
You can then replace the paths in `conf/dset/auto_extra.yaml`, `conf/dset/auto_extra_test.yaml`
and `conf/dset/aetl.yaml` (this last one was using 10 mixes instead of 6 for each song).

### Dataset metadata cache

Datasets are scanned the first time they are used to determine the files and their durations.
If you change a dataset and need a rescan, just delete the `metadata` folder.

## A short intro to Dora

I use [Dora][dora] for all the of experiments (XPs) management. You should have a look at the Dora README
to learn about the tool. Here is a quick summary of what to know:

- An XP is a unique set of hyper-parameters with a given signature. The signature is a hash of
    those hyper-parameters. I will always refer to an XP with its signature, e.g. `9357e12e`.
    We will see after that you can retrieve the hyper-params and re-rerun it in a single command.
- In fact, the hash is defined as a delta between the base config and the one obtained with
    the config overrides you passed from the command line.
    **This means you must never change the `conf/**.yaml` files directly.**,
    except for editing things like paths. Changing the default values in the config files means
    the XP signature won't reflect that change, and wrong checkpoints might be reused.
    I know, this is annoying, but the reason is that otherwise, any change to the config file would
    mean that all XPs ran so far would see their signature change.

### Dora commands

Run `tar xvf outputs.tar.gz`. This will initialize the Dora XP repository, so that Dora knows
which hyper-params match the signature like `9357e12e`. Once you have done that, you should be able
to run the following:

```bash
dora info -f 81de367c  # this will show the hyper-parameter used by a specific XP.
                       # Be careful some overrides might present twice, and the right most one
                       # will give you the right value for it.
dora run -d -f 81de367c   # run an XP with the hyper-parameters from XP 81de367c.
                          # `-d` is for distributed, it will use all available GPUs.
dora run -d -f 81de367c hdemucs.channels=32  # start from the config of XP 81de367c but change some hyper-params.
                                             # This will give you a new XP with a new signature (here 3fe9c332).
```

An XP runs from a specific folder based on its signature, by default under the `outputs/` folder.
You can safely interrupt a training and resume it, it will reuse any existing checkpoint, as it will
reuse the same folder.
If you made some change to the code and need to ignore a previous checkpoint you can use `dora run --clear [RUN ARGS]`.

If you have a Slurm cluster, you can also use the `dora grid` command, e.g. `dora grid mdx`.
Please refer to the [Dora documentation][dora] for more information.

## Hyper parameters

Have a look at [conf/config.yaml](../conf/config.yaml) for a list of all the hyper-parameters you can override.
If you are not familiar with [Hydra](https://github.com/facebookresearch/hydra), go checkout their page
to be familiar with how to provide overrides for your trainings.


## Model architecture

A number of architectures are supported. You can select one with `model=NAME`, and have a look
in [conf/config.yaml'(../conf/config.yaml) for each architecture specific hyperparams.
Those specific params will be always prefixed with the architecture name when passing the override
from the command line or in grid files. Here is the list of models:

- demucs: original time-only Demucs.
- hdemucs: Hybrid Demucs (v3).
- torch_hdemucs: Same as Hybrid Demucs, but using [torchaudio official implementation](https://pytorch.org/audio/stable/tutorials/hybrid_demucs_tutorial.html).
- htdemucs: Hybrid Transformer Demucs (v4).

### Storing config in files

As mentioned earlier, you should never change the base config files. However, you can use Hydra config groups
in order to store variants you often use. If you want to create a new variant combining multiple hyper-params,
copy the file `conf/variant/example.yaml` to `conf/variant/my_variant.yaml`, and then you can use it with

```bash
dora run -d variant=my_variant
```

Once you have created this file, you should not edit it once you have started training models with it.


## Fine tuning

If a first model is trained, you can fine tune it with other settings (e.g. automix dataset) with

```bash
dora run -d -f 81de367c continue_from=81de367c dset=auto_mus variant=finetune
````

Note that you need both `-f 81de367c` and `continue_from=81de367c`. The first one indicates
that the hyper-params of `81de367c` should be used as a starting point for the config.
The second indicates that the weights from `81de367c` should be used as a starting point for the solver.


## Model evaluation

Your model will be evaluated automatically with the new SDR definition from MDX every 20 epochs.
Old style SDR (which is quite slow) will only happen at the end of training.

## Model Export


In order to use your models with other commands (such as the `demucs` command for separation) you must
export it. For that run

```bash
python3 -m tools.export 9357e12e [OTHER SIGS ...]  # replace with the appropriate signatures.
```

The models will be stored under `release_models/`. You can use them with the `demucs` separation command with the following flags:
```bash
demucs --repo ./release_models -n 9357e12e my_track.mp3
```

### Bag of models

If you want to combine multiple models, potentially with different weights for each source, you can copy
`demucs/remote/mdx.yaml` to `./release_models/my_bag.yaml`. You can then edit the list of models (all models used should have been exported first) and the weights per source and model (list of list, outer list is over models, inner list is over sources). You can then use your bag of model as

```bash
demucs --repo ./release_models -n my_bag my_track.mp3
```

## Model evaluation

You can evaluate any pre-trained model or bag of models using the following command:
```bash
python3 -m tools.test_pretrained -n NAME_OF_MODEL [EXTRA ARGS]
```
where `NAME_OF_MODEL` is either the name of the bag (e.g. `mdx`, `repro_mdx_a`),
or a single Dora signature of one of the model of the bags. You can pass `EXTRA ARGS` to customize
the test options, like the number of random shifts (e.g. `test.shifts=2`). This will compute the old-style
SDR and can take quite  bit of time.

For custom models that were trained locally, you will need to indicate that you wish
to use the local model repositories, with the `--repo ./release_models` flag, e.g.,
```bash
python3 -m tools.test_pretrained --repo ./release_models -n my_bag
```


## API to retrieve the model

You can retrieve officially released models in Python using the following API:
```python
from demucs import pretrained
from demucs.apply import apply_model
bag = pretrained.get_model('htdemucs')    # for a bag of models or a named model
                                          # (which is just a bag with 1 model).
model = pretrained.get_model('955717e8')  # using the signature for single models.

bag.models                       # list of individual models
stems = apply_model(model, mix)  # apply the model to the given mix.
```

## Model Zoo

### Hybrid Transformer Demucs

The configuration for the Hybrid Transformer models are available in:

```shell
dora grid mmi --dry_run --init
dora grid mmi_ft --dry_run --init  # fined tuned on each sources.
```

We release in particular `955717e8`, Hybrid Transformer Demucs using 5 layers, 512 channels, 10 seconds training segment length. We also release its fine tuned version, with one model
for each source `f7e0c4bc`, `d12395a8`, `92cfc3b6`, `04573f0d` (drums, bass, other, vocals).
The model `955717e8` is also named `htdemucs`, while the bag of models is provided
as `htdemucs_ft`.

We also release `75fc33f5`, a regular Hybrid Demucs trained on the same dataset,
available as `hdemucs_mmi`.



### Models from the MDX Competition 2021

  
Here is a short descriptions of the models used for the MDX submission, either Track A (MusDB HQ only)
or Track B (extra training data allowed). Training happen in two stage, with the second stage
being the fine tunining on the automix generated dataset.
All the fine tuned models are available on our AWS repository
(you can retrieve it with `demucs.pretrained.get_model(SIG)`). The bag of models are available
by doing `demucs.pretrained.get_model(NAME)` with `NAME` begin either `mdx` (for Track A) or `mdx_extra`
(for Track B).

#### Track A

The 4 models are:

- `0d19c1c6`: fine-tuned on automix dataset from `9357e12e`
- `7ecf8ec1`: fine-tuned on automix dataset from `e312f349`
- `c511e2ab`: fine-tuned on automix dataset from `81de367c`
- `7d865c68`: fine-tuned on automix dataset from `80a68df8`

The 4 initial models (before fine tuning are):

- `9357e12e`: 64ch time domain only improved Demucs, with new residual branches, group norm,
  and singular value penalty.
- `e312f349`: 64ch time domain only improved, with new residual branches, group norm,
  and singular value penalty, trained with a loss that focus only on drums and bass.
- `81de367c`: 48ch hybrid model , with residual branches, group norm,
  singular value penalty penalty and amplitude spectrogram.
- `80a68df8`: same as b5559babb but using CaC and different
  random seed, as well different weigths per frequency bands in outermost layers.

The hybrid models are combined with equal weights for all sources except for the bass.
`0d19c1c6` (time domain) is used for both drums and bass. `7ecf8ec1` is used only for the bass.

You can see all the hyper parameters at once with (one common line for all common hyper params, and then only shows
the hyper parameters that differs), along with the DiffQ variants that are used for the `mdx_q` models:
```
dora grid mdx --dry_run --init
dora grid mdx --dry_run --init
```

#### Track B

- `e51eebcc`
- `a1d90b5c`
- `5d2d6c55`
- `cfa93e08`

All the models are 48ch hybrid demucs with different random seeds. Two of them
are using CaC, and two are using amplitude spectrograms with masking.
All the models are combined with equal weights for all sources.

Things are a bit messy for Track B, there was a lot of fine tuning
over different datasets. I won't describe the entire genealogy of models here,
but all the information can be accessed with the `dora info -f SIG` command.

Similarly you can do (those will contain a few extra lines, for training without the MusDB test set as training, and extra DiffQ XPs):
```
dora grid mdx_extra --dry_run --init
```

### Reproducibility and Ablation

I updated the paper to report numbers with a more homogeneous setup than the one used for the competition.
On MusDB HQ, I still need to use a combination of time only and hybrid models to achieve the best performance.
The experiments are provided in the grids [repro.py](../demucs/grids/repro.py) and
[repro_ft._py](../demucs/grids/repro_ft.py) for the fine tuning on the realistic mix datasets.

The new bag of models reaches an SDR of 7.64 (vs. 7.68 for the original track A model). It uses
2 time only models trained with residual branches, local attention and the SVD penalty,
along with 2 hybrid models, with the same features, and using CaC representation.
We average the performance of all the models with the same weight over all sources, unlike
what was done for the original track A model. We trained for 600 epochs, against 360 before.

The new bag of model is available as part of the pretrained model as `repro_mdx_a`.
The time only bag is named `repro_mdx_a_time_only`, and the hybrid only `repro_mdx_a_hybrid_only`.
Checkout the paper for more information on the training.

[dora]: https://github.com/facebookresearch/dora
