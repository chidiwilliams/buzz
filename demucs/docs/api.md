# Demucs APIs

## Quick start

Notes: Type hints have been added to all API functions. It is recommended to check them before passing parameters to a function as some arguments only support limited types (e.g. parameter `repo` of method `load_model` only support type `pathlib.Path`).

1. The first step is to import api module:

```python
import demucs.api
```

2. Then initialize the `Separator`. Parameters which will be served as default values for methods can be passed. Model should be specified.

```python
# Initialize with default parameters:
separator = demucs.api.Separator()

# Use another model and segment:
separator = demucs.api.Separator(model="mdx_extra", segment=12)

# You can also use other parameters defined
```

3. Separate it!

```python
# Separating an audio file
origin, separated = separator.separate_audio_file("file.mp3")

# Separating a loaded audio
origin, separated = separator.separate_tensor(audio)

# If you encounter an error like CUDA out of memory, you can use this to change parameters like `segment`:
separator.update_parameter(segment=smaller_segment)
```

4. Save audio

```python
# Remember to create the destination folder before calling `save_audio`
# Or you are likely to recieve `FileNotFoundError`
for file, sources in separated:
    for stem, source in sources.items():
        demucs.api.save_audio(source, f"{stem}_{file}", samplerate=separator.samplerate)
```

## API References

The types of each parameter and return value is not listed in this document. To know the exact type of them, please read the type hints in api.py (most modern code editors support inferring types based on type hints).

### `class Separator`

The base separator class

##### Parameters

model: Pretrained model name or signature. Default is htdemucs.

repo: Folder containing all pre-trained models for use.

segment: Length (in seconds) of each segment (only available if `split` is `True`). If not specified, will use the command line option.

shifts: If > 0, will shift in time `wav` by a random amount between 0 and 0.5 sec and apply the oppositve shift to the output. This is repeated `shifts` time and all predictions are averaged. This effectively makes the model time equivariant and improves SDR by up to 0.2 points. If not specified, will use the command line option.

split: If True, the input will be broken down into small chunks (length set by `segment`) and predictions will be performed individually on each and concatenated. Useful for model with large memory footprint like Tasnet. If not specified, will use the command line option.

overlap: The overlap between the splits. If not specified, will use the command line option.

device (torch.device, str, or None): If provided, device on which to execute the computation, otherwise `wav.device` is assumed. When `device` is different from `wav.device`, only local computations will be on `device`, while the entire tracks will be stored on `wav.device`. If not specified, will use the command line option.

jobs: Number of jobs. This can increase memory usage but will be much faster when multiple cores are available. If not specified, will use the command line option.

callback: A function will be called when the separation of a chunk starts or finished. The argument passed to the function will be a dict. For more information, please see the Callback section.

callback_arg: A dict containing private parameters to be passed to callback function. For more information, please see the Callback section.

progress: If true, show a progress bar.

##### Notes for callback

The function will be called with only one positional parameter whose type is `dict`. The `callback_arg` will be combined with information of current separation progress. The progress information will override the values in `callback_arg` if same key has been used. To abort the separation, raise an exception in `callback` which should be handled by yourself if you want your codes continue to function.

Progress information contains several keys (These keys will always exist):
- `model_idx_in_bag`: The index of the submodel in `BagOfModels`. Starts from 0.
- `shift_idx`: The index of shifts. Starts from 0.
- `segment_offset`: The offset of current segment. If the number is 441000, it doesn't mean that it is at the 441000 second of the audio, but the "frame" of the tensor.
- `state`: Could be `"start"` or `"end"`.
- `audio_length`: Length of the audio (in "frame" of the tensor).
- `models`: Count of submodels in the model.

#### `property samplerate`

A read-only property saving sample rate of the model requires. Will raise a warning if the model is not loaded and return the default value.

#### `property audio_channels`

A read-only property saving audio channels of the model requires. Will raise a warning if the model is not loaded and return the default value.

#### `property model`

A read-only property saving the model.

#### `method update_parameter()`

Update the parameters of separation.

##### Parameters

segment: Length (in seconds) of each segment (only available if `split` is `True`). If not specified, will use the command line option.

shifts: If > 0, will shift in time `wav` by a random amount between 0 and 0.5 sec and apply the oppositve shift to the output. This is repeated `shifts` time and all predictions are averaged. This effectively makes the model time equivariant and improves SDR by up to 0.2 points. If not specified, will use the command line option.

split: If True, the input will be broken down into small chunks (length set by `segment`) and predictions will be performed individually on each and concatenated. Useful for model with large memory footprint like Tasnet. If not specified, will use the command line option.

overlap: The overlap between the splits. If not specified, will use the command line option.

device (torch.device, str, or None): If provided, device on which to execute the computation, otherwise `wav.device` is assumed. When `device` is different from `wav.device`, only local computations will be on `device`, while the entire tracks will be stored on `wav.device`. If not specified, will use the command line option.

jobs: Number of jobs. This can increase memory usage but will be much faster when multiple cores are available. If not specified, will use the command line option.

callback: A function will be called when the separation of a chunk starts or finished. The argument passed to the function will be a dict. For more information, please see the Callback section.

callback_arg: A dict containing private parameters to be passed to callback function. For more information, please see the Callback section.

progress: If true, show a progress bar.

##### Notes for callback

The function will be called with only one positional parameter whose type is `dict`. The `callback_arg` will be combined with information of current separation progress. The progress information will override the values in `callback_arg` if same key has been used. To abort the separation, raise an exception in `callback` which should be handled by yourself if you want your codes continue to function.

Progress information contains several keys (These keys will always exist):
- `model_idx_in_bag`: The index of the submodel in `BagOfModels`. Starts from 0.
- `shift_idx`: The index of shifts. Starts from 0.
- `segment_offset`: The offset of current segment. If the number is 441000, it doesn't mean that it is at the 441000 second of the audio, but the "frame" of the tensor.
- `state`: Could be `"start"` or `"end"`.
- `audio_length`: Length of the audio (in "frame" of the tensor).
- `models`: Count of submodels in the model.

#### `method separate_tensor()`

Separate an audio.

##### Parameters

wav: Waveform of the audio. Should have 2 dimensions, the first is each audio channel, while the second is the waveform of each channel. e.g. `tuple(wav.shape) == (2, 884000)` means the audio has 2 channels.

sr: Sample rate of the original audio, the wave will be resampled if it doesn't match the model.

##### Returns

A tuple, whose first element is the original wave and second element is a dict, whose keys are the name of stems and values are separated waves. The original wave will have already been resampled.

##### Notes

Use this function with cautiousness. This function does not provide data verifying.

#### `method separate_audio_file()`

Separate an audio file. The method will automatically read the file.

##### Parameters

wav: Path of the file to be separated.

##### Returns

A tuple, whose first element is the original wave and second element is a dict, whose keys are the name of stems and values are separated waves. The original wave will have already been resampled.

### `function save_audio()`

Save audio file.

##### Parameters

wav: Audio to be saved

path: The file path to be saved. Ending must be one of `.mp3` and `.wav`.

samplerate: File sample rate.

bitrate: If the suffix of `path` is `.mp3`, it will be used to specify the bitrate of mp3.

clip: Clipping preventing strategy.

bits_per_sample: If the suffix of `path` is `.wav`, it will be used to specify the bit depth of wav.

as_float: If it is True and the suffix of `path` is `.wav`, then `bits_per_sample` will be set to 32 and will write the wave file with float format.

##### Returns

None

### `function list_models()`

List the available models. Please remember that not all the returned models can be successfully loaded.

##### Parameters

repo: The repo whose models are to be listed.

##### Returns

A dict with two keys ("single" for single models and "bag" for bag of models). The values are lists whose components are strs.