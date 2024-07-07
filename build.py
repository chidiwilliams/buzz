import subprocess


def build(setup_kwargs):
    subprocess.call(["make", "buzz/whisper_cpp.py"])
    subprocess.call(["make", "translation_mo"])


if __name__ == "__main__":
    build({})
