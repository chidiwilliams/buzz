# Music DemiXing challenge (MDX)

If you want to use Demucs for the [MDX challenge](https://www.aicrowd.com/challenges/music-demixing-challenge-ismir-2021),
please follow the instructions hereafter

## Installing Demucs

Follow the instructions from the [main README](https://github.com/facebookresearch/demucs#requirements)
in order to setup Demucs using Anaconda. You will need the full setup up for training, including soundstretch.

## Getting MusDB-HQ

Download [MusDB-HQ](https://zenodo.org/record/3338373) to some folder and unzip it.

## Training Demucs

Train Demucs (you might need to change the batch size depending on the number of GPUs available).
It seems 48 channels is enough to get the best performance on MusDB-HQ, and training will faster
and less memory demanding. In any case, the 64 channels versions is timing out on the challenge.
```bash
./run.py --channels=48 --batch_size 64 --musdb=PATH_TO_MUSDB --is_wav [EXTRA_FLAGS]
```

### Post training

Once the training is completed, a new model file will be exported in `models/`.

You can look at the SDR on the MusDB dataset using `python result_table.py`.


### Evaluate and export a model before training is over

If you want to export a model before training is complete, use the following command:
```bash
python -m demucs [ALL EXACT TRAINING FLAGS] --save_model
```
You can also pass the `--half` flag, in order to save weights in half precision. This will divide the model size by 2 and won't impact SDR.

Once this is done, you can partially evaluate a model with
```bash
./run.py --test NAME_OF_MODEL.th --musdb=PATH_TO_MUSDB --is_wav
```

**Note:** `NAME_OF_MODEL.th` is given relative to the models folder (given by `--models`, defaults to `models/`), so don't include it in the name.


### Training smaller models

If you want to quickly test idea, I would recommend training a 16 kHz model, and testing if things work there or not, before training the full 44kHz model. You can train one of those with
```bash
./run.py --channels=32 --samplerate 16000 --samples 160000 --data_stride 16000 --depth=5 --batch_size 64 --repitch=0 --musdb=PATH_TO_MUSDB --is_wav [EXTRA_FLAGS]
```
(repitch must be turned off, because things will break at 16kHz).

## Submitting your model

1. Git clone [the Music Demixing Challenge - Starter Kit - Demucs Edition](https://github.com/adefossez/music-demixing-challenge-starter-kit).
2. Inside the starter kit, create a `models/` folder and copy over the trained model from the Demucs repo (renaming
it for instance `my_model.th`)
3. Inside the `test_demuc.py` file, change the function `prediction_setup`: comment the loading
of the pre-trained model, and uncomment the code to load your own model.
4. Edit the file `aicrowd.json` with your username.
5. Install [git-lfs](https://git-lfs.github.com/). Then run

```bash
git lfs install
git add models/
git add -u .
git commit -m "My Demucs submission"
```
6. Follow the [submission instructions](https://github.com/AIcrowd/music-demixing-challenge-starter-kit/blob/master/docs/SUBMISSION.md).

Best of luck 🤞
