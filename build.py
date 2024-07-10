import subprocess


def build(setup_kwargs):
    subprocess.call(["make", "buzz/whisper_cpp.py"])


if __name__ == "__main__":
    build({})
