import os
from typing import List


def file_path_as_title(file_path: str):
    return os.path.basename(file_path)


def file_paths_as_title(file_paths: List[str]):
    return ", ".join([file_path_as_title(path) for path in file_paths])
