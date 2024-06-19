from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QWidget

from buzz.transcriber.transcriber import Task, TASK_LABEL_TRANSLATIONS


class TasksComboBox(QComboBox):
    """TasksComboBox displays a list of tasks available to use with Whisper"""

    taskChanged = pyqtSignal(Task)

    def __init__(self, default_task: Task, parent: Optional[QWidget], *args) -> None:
        super().__init__(parent, *args)
        self.tasks = [i for i in Task]
        self.addItems(map(lambda task: TASK_LABEL_TRANSLATIONS[task], self.tasks))
        self.currentIndexChanged.connect(self.on_index_changed)
        self.setCurrentText(TASK_LABEL_TRANSLATIONS[default_task])

    def on_index_changed(self, index: int):
        self.taskChanged.emit(self.tasks[index])
