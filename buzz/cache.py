import json
import logging
import os
import pickle
from typing import List

from platformdirs import user_cache_dir

from buzz.transcriber.transcriber import FileTranscriptionTask


class TasksCache:
    def __init__(self, cache_dir=user_cache_dir("Buzz")):
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_dir = cache_dir
        self.pickle_cache_file_path = os.path.join(cache_dir, "tasks")
        self.tasks_list_file_path = os.path.join(cache_dir, "tasks.json")

    def save(self, tasks: List[FileTranscriptionTask]):
        self.save_json_tasks(tasks=tasks)

    def load(self) -> List[FileTranscriptionTask]:
        if os.path.exists(self.tasks_list_file_path):
            return self.load_json_tasks()

        try:
            with open(self.pickle_cache_file_path, "rb") as file:
                return pickle.load(file)
        except FileNotFoundError:
            return []
        except (
            pickle.UnpicklingError,
            AttributeError,
            ValueError,
        ):  # delete corrupted cache
            os.remove(self.pickle_cache_file_path)
            return []

    def load_json_tasks(self) -> List[FileTranscriptionTask]:
        task_ids: List[int]
        try:
            with open(self.tasks_list_file_path) as file:
                task_ids = json.load(file)
        except json.JSONDecodeError:
            logging.debug(
                "Got JSONDecodeError while reading tasks list file path, "
                "resetting cache..."
            )
            task_ids = []

        tasks = []
        for task_id in task_ids:
            try:
                with open(self.get_task_path(task_id=task_id)) as file:
                    tasks.append(FileTranscriptionTask.from_json(file.read()))
            except (FileNotFoundError, json.JSONDecodeError):
                pass

        return tasks

    def save_json_tasks(self, tasks: List[FileTranscriptionTask]):
        json_str = json.dumps([task.id for task in tasks])
        with open(self.tasks_list_file_path, "w") as file:
            file.write(json_str)

        for task in tasks:
            file_path = self.get_task_path(task_id=task.id)
            json_str = task.to_json()
            with open(file_path, "w") as file:
                file.write(json_str)

    def get_task_path(self, task_id: int):
        path = os.path.join(self.cache_dir, "transcriptions", f"{task_id}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def clear(self):
        if os.path.exists(self.pickle_cache_file_path):
            os.remove(self.pickle_cache_file_path)
