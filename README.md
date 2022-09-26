# Buzz

Buzz transcribes audio from your computer's microphones to text using OpenAI's [Whisper](https://github.com/openai/whisper). Buzz works by splitting audio recordings into chunks and transcribing the chunks to text using Whisper.

## Requirements

To set up Buzz, first install ffmpeg ([needed to run Whisper](https://github.com/openai/whisper#setup)).

```text
# on Ubuntu or Debian
sudo apt update && sudo apt install ffmpeg

# on MacOS using Homebrew (https://brew.sh/)
brew install ffmpeg

# on Windows using Chocolatey (https://chocolatey.org/)
choco install ffmpeg

# on Windows using Scoop (https://scoop.sh/)
scoop install ffmpeg
```

## Build

To build Buzz, run:

```shell
pip install -r requirements.txt
make buzz
```
