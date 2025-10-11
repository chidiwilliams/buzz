import subprocess


def build(setup_kwargs):
    subprocess.call(["make", "buzz/whisper_cpp"])


if __name__ == "__main__":
    build({})
