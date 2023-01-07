import logging
import os
import pickle
from typing import List

from platformdirs import user_cache_dir

from .transcriber import FileTranscriptionTask


class TasksCache:
    def __init__(self, cache_dir=user_cache_dir('Buzz')):
        os.makedirs(cache_dir, exist_ok=True)
        self.file_path = os.path.join(cache_dir, 'tasks')

    def save(self, tasks: List[FileTranscriptionTask]):
        with open(self.file_path, 'wb') as file:
            pickle.dump(tasks, file)

    def load(self) -> List[FileTranscriptionTask]:
        try:
            with open(self.file_path, 'rb') as file:
                return pickle.load(file)
        except FileNotFoundError:
            return []
        except (pickle.UnpicklingError, AttributeError, ValueError):  # delete corrupted cache
            os.remove(self.file_path)
            return []

    def clear(self):
        if os.path.exists(self.file_path):
            os.remove(self.file_path)
