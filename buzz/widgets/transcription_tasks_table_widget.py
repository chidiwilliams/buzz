import enum
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import auto
from typing import Optional, List
from uuid import UUID

from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtCore import pyqtSignal, QModelIndex
from PyQt6.QtSql import QSqlTableModel, QSqlRecord
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QMenu,
    QHeaderView,
    QTableView,
    QAbstractItemView,
    QStyledItemDelegate,
)

from buzz.db.entity.transcription import Transcription
from buzz.locale import _
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import FileTranscriptionTask, Task, TASK_LABEL_TRANSLATIONS
from buzz.widgets.record_delegate import RecordDelegate
from buzz.widgets.transcription_record import TranscriptionRecord


class Column(enum.Enum):
    ID = 0
    ERROR_MESSAGE = 1
    EXPORT_FORMATS = 2
    FILE = 3
    OUTPUT_FOLDER = 4
    PROGRESS = 5
    LANGUAGE = 6
    MODEL_TYPE = 7
    SOURCE = 8
    STATUS = 9
    TASK = 10
    TIME_ENDED = 11
    TIME_QUEUED = 12
    TIME_STARTED = 13
    URL = 14
    WHISPER_MODEL_SIZE = 15
    HUGGING_FACE_MODEL_ID = 16
    WORD_LEVEL_TIMINGS = 17
    EXTRACT_SPEECH = 18
    NAME = 19
    NOTES = 20


@dataclass
class ColDef:
    id: str
    header: str
    column: Column
    width: Optional[int] = None
    delegate: Optional[QStyledItemDelegate] = None
    hidden_toggleable: bool = True


def format_record_status_text(record: QSqlRecord) -> str:
    status = FileTranscriptionTask.Status(record.value("status"))
    match status:
        case FileTranscriptionTask.Status.IN_PROGRESS:
            in_progress_label = _("In Progress")
            return f'{in_progress_label} ({record.value("progress") :.0%})'
        case FileTranscriptionTask.Status.COMPLETED:
            status = _("Completed")
            started_at = record.value("time_started")
            completed_at = record.value("time_ended")
            if started_at != "" and completed_at != "":
                status += f" ({TranscriptionTasksTableWidget.format_timedelta(datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at))})"
            return status
        case FileTranscriptionTask.Status.FAILED:
            failed_label = _("Failed")
            return f'{failed_label} ({record.value("error_message")})'
        case FileTranscriptionTask.Status.CANCELED:
            return _("Canceled")
        case FileTranscriptionTask.Status.QUEUED:
            return _("Queued")
        case _: # Case to handle UNKNOWN status
            return ""

column_definitions = [
    ColDef(
        id="file_name",
        header=_("File Name / URL"),
        column=Column.FILE,
        width=400,
        delegate=RecordDelegate(
            text_getter=lambda record: record.value("name") or (
                record.value("url") if record.value("url") != ""
                else os.path.basename(record.value("file"))
            )
        ),
        hidden_toggleable=False,
    ),
    ColDef(
        id="model",
        header=_("Model"),
        column=Column.MODEL_TYPE,
        width=180,
        delegate=RecordDelegate(
            text_getter=lambda record: str(TranscriptionRecord.model(record))
        ),
    ),
    ColDef(
        id="task",
        header=_("Task"),
        column=Column.TASK,
        width=120,
        delegate=RecordDelegate(
            text_getter=lambda record: TASK_LABEL_TRANSLATIONS[Task(record.value("task"))]
        ),
    ),
    ColDef(
        id="status",
        header=_("Status"),
        column=Column.STATUS,
        width=180,
        delegate=RecordDelegate(text_getter=format_record_status_text),
        hidden_toggleable=True,
    ),

    ColDef(
        id="date_completed",
        header=_("Date Completed"),
        column=Column.TIME_ENDED,
        width=180,
        delegate=RecordDelegate(
            text_getter=lambda record: datetime.fromisoformat(
                record.value("time_ended")
            ).strftime("%Y-%m-%d %H:%M:%S")
            if record.value("time_ended") != ""
            else ""
        ),
    ),    ColDef(
        id="date_added",
        header=_("Date Added"),
        column=Column.TIME_QUEUED,
        width=180,
        delegate=RecordDelegate(
            text_getter=lambda record: datetime.fromisoformat(
                record.value("time_queued")
            ).strftime("%Y-%m-%d %H:%M:%S")
        ),
    ),
    ColDef(
        id="notes",
        header=_("Notes"),
        column=Column.NOTES,
        width=300,
        delegate=RecordDelegate(
            text_getter=lambda record: record.value("notes") or ""
        ),
        hidden_toggleable=True,
    ),
]

class TranscriptionTasksTableHeaderView(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        # Add reset column order option
        menu.addAction(_("Reset Column Order")).triggered.connect(self.parent().reset_column_order)
        menu.addSeparator()
        
        # Add column visibility toggles
        for definition in column_definitions:
            if definition.hidden_toggleable:
                action = menu.addAction(definition.header)
                action.setCheckable(True)
                action.setChecked(not self.parent().isColumnHidden(definition.column.value))
                action.toggled.connect(
                    lambda checked, column_index=definition.column.value: self.on_column_checked(
                        column_index, checked
                    )
                )
        menu.exec(event.globalPos())

    def on_column_checked(self, column_index: int, checked: bool):
        # Find the column definition for this index
        column_def = None
        for definition in column_definitions:
            if definition.column.value == column_index:
                column_def = definition
                break
        
        print(f"[DEBUG] Toggling column {column_def.id if column_def else 'unknown'} (index {column_index}) to {'visible' if checked else 'hidden'}")
        
        # If we're hiding the column, save its current width first
        if not checked and not self.parent().isColumnHidden(column_index):
            current_width = self.parent().columnWidth(column_index)
            if current_width > 0:  # Only save if there's a meaningful width
                self.parent().settings.begin_group(self.parent().settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS)
                self.parent().settings.settings.setValue(column_def.id, current_width)
                self.parent().settings.end_group()
                print(f"[DEBUG] Saved width {current_width} for column {column_def.id} before hiding")
        
        # Update the visibility state on the table view (not header view)
        self.parent().setColumnHidden(column_index, not checked)
        
        # Save current column order before any reloading
        self.parent().save_column_order()
        
        # Save both visibility and widths after the change
        self.parent().save_column_visibility()
        self.parent().save_column_widths()
        
        # Ensure settings are synchronized
        self.parent().settings.settings.sync()
        
        # Force a complete refresh of the table
        self.parent().viewport().update()
        self.parent().repaint()
        self.parent().horizontalHeader().update()
        self.parent().updateGeometry()
        self.parent().adjustSize()
        
        # Force a model refresh to ensure the view is updated
        self.parent().model().layoutChanged.emit()

        self.parent().reload_column_order_from_settings()
        
        print(f"[DEBUG] After toggle: column {column_index} hidden = {self.parent().isColumnHidden(column_index)}")

class TranscriptionTasksTableWidget(QTableView):
    return_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.transcription_service = None

        self.setHorizontalHeader(TranscriptionTasksTableHeaderView(Qt.Orientation.Horizontal, self))

        self._model = QSqlTableModel()
        self._model.setTable("transcription")
        self._model.setEditStrategy(QSqlTableModel.EditStrategy.OnManualSubmit)
        self._model.setSort(Column.TIME_QUEUED.value, Qt.SortOrder.DescendingOrder)

        self.setModel(self._model)

        for i in range(self.model().columnCount()):
            self.hideColumn(i)

        self.settings = Settings()

        # Set up column headers and delegates
        for definition in column_definitions:
            self.model().setHeaderData(
                definition.column.value,
                Qt.Orientation.Horizontal,
                definition.header,
            )
            if definition.delegate is not None:
                self.setItemDelegateForColumn(
                    definition.column.value, definition.delegate
                )

        # Load column visibility
        self.load_column_visibility()

        self.model().select()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().hide()
        self.setAlternatingRowColors(True)
        
        # Enable column sorting and moving
        self.setSortingEnabled(True)
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setSectionsClickable(True)
        self.horizontalHeader().setSortIndicatorShown(True)

        # Connect signals for column resize and move
        self.horizontalHeader().sectionResized.connect(self.on_column_resized)
        self.horizontalHeader().sectionMoved.connect(self.on_column_moved)

        # Load saved column order and widths
        self.load_column_order()
        self.load_column_widths()

        
        # Reload column visibility after all reordering is complete
        self.load_column_visibility()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        # Add transcription actions if a row is selected
        selected_rows = self.selectionModel().selectedRows()
        if selected_rows:
            transcription = self.transcription(selected_rows[0])
            
            # Add restart/continue action for failed/canceled tasks
            # Print the status of the transcription
            print(f"[DEBUG] Transcription status: {transcription.status}")
            if transcription.status in ["failed", "canceled"]:
                restart_action = menu.addAction(_("Restart Transcription"))
                restart_action.triggered.connect(self.on_restart_transcription_action)
                menu.addSeparator()
            
            rename_action = menu.addAction(_("Rename"))
            rename_action.triggered.connect(self.on_rename_action)
            
            notes_action = menu.addAction(_("Add/Edit Notes"))
            notes_action.triggered.connect(self.on_notes_action)
        
        menu.exec(event.globalPos())

    def save_column_visibility(self):
        self.settings.begin_group(
            Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY
        )
        for definition in column_definitions:
            self.settings.settings.setValue(
                definition.id, not self.isColumnHidden(definition.column.value)
            )
        self.settings.end_group()

    def on_column_resized(self, logical_index: int, old_size: int, new_size: int):
        """Handle column resize events"""
        self.save_column_widths()

    def on_column_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int):
        """Handle column move events"""
        self.save_column_order()
        # Refresh visibility after column move to ensure it's maintained
        self.load_column_visibility()

    def save_column_widths(self):
        """Save current column widths to settings"""
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS)
        for definition in column_definitions:
            # Only save width if column is visible and has a meaningful width
            if not self.isColumnHidden(definition.column.value):
                width = self.columnWidth(definition.column.value)
                if width > 0:  # Only save if there's a meaningful width
                    self.settings.settings.setValue(definition.id, width)
        self.settings.end_group()

    def save_column_order(self):
        """Save current column order to settings"""
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER)
        header = self.horizontalHeader()
        for visual_index in range(header.count()):
            logical_index = header.logicalIndex(visual_index)
            # Find the column definition for this logical index
            for definition in column_definitions:
                if definition.column.value == logical_index:
                    self.settings.settings.setValue(definition.id, visual_index)
                    break
        self.settings.end_group()

    def load_column_widths(self):
        """Load saved column widths from settings"""
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS)
        for definition in column_definitions:
            if definition.width is not None:  # Only load if column has a default width
                saved_width = self.settings.settings.value(definition.id, definition.width)
                if saved_width is not None:
                    self.setColumnWidth(definition.column.value, int(saved_width))
        self.settings.end_group()

    def load_column_visibility(self):
        """Load saved column visibility from settings"""
        print("[DEBUG] load_column_visibility() called")
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY)
        for definition in column_definitions:
            visible = True
            if definition.hidden_toggleable:
                value = self.settings.settings.value(definition.id, "true")
                visible = value in {"true", "True", True}
                print(f"[DEBUG] Column '{definition.id}': settings value = {value}, visible = {visible}")
            
            self.setColumnHidden(definition.column.value, not visible)
        self.settings.end_group()
        
        # Force a refresh of the table layout
        self.horizontalHeader().update()
        self.viewport().update()
        self.updateGeometry()
        print("[DEBUG] load_column_visibility() finished")

    def load_column_order(self):
        """Load saved column order from settings"""
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER)
        
        # Create a mapping of column IDs to their saved visual positions
        column_positions = {}
        for definition in column_definitions:
            saved_position = self.settings.settings.value(definition.id)
            if saved_position is not None:
                column_positions[definition.column.value] = int(saved_position)
        
        self.settings.end_group()
        
        # Apply the saved order
        if column_positions:
            header = self.horizontalHeader()
            for logical_index, visual_position in column_positions.items():
                if 0 <= visual_position < header.count():
                    header.moveSection(header.visualIndex(logical_index), visual_position)
    
    def reset_column_order(self):
        """Reset column order to default"""

        # Reset column widths to defaults
        for definition in column_definitions:
            if definition.width is not None:
                self.setColumnWidth(definition.column.value, definition.width)

        # Show all columns
        for definition in column_definitions:
            self.setColumnHidden(definition.column.value, False)

        # Restore default column order
        header = self.horizontalHeader()
        # Move each section to its default position in order
        # To avoid index shifting, move from left to right
        for target_visual_index, definition in enumerate(column_definitions):
            logical_index = definition.column.value
            current_visual_index = header.visualIndex(logical_index)
            if current_visual_index != target_visual_index:
                header.moveSection(current_visual_index, target_visual_index)

        # Clear saved settings
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER)
        self.settings.settings.remove("")
        self.settings.end_group()

        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS)
        self.settings.settings.remove("")
        self.settings.end_group()

        # Save the reset state for both visibility and widths
        self.save_column_visibility()
        self.save_column_widths()

        # Force a refresh of the table layout
        self.horizontalHeader().update()
        self.viewport().update()
        self.updateGeometry()

    def reload_column_order_from_settings(self):
        """Reload column order, width, and visibility from settings"""

        # --- Load column visibility ---
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_VISIBILITY)
        visibility_settings = {}
        for definition in column_definitions:
            vis = self.settings.settings.value(definition.id)
            if vis is not None:
                visibility_settings[definition.id] = str(vis).lower() not in ("0", "false", "no")
        self.settings.end_group()

        # --- Load column widths ---
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_WIDTHS)
        width_settings = {}
        for definition in column_definitions:
            width = self.settings.settings.value(definition.id)
            if width is not None:
                try:
                    width_settings[definition.id] = int(width)
                except Exception:
                    print(f"[DEBUG] Invalid width for column '{definition.id}': {width}")
        self.settings.end_group()

        # --- Load column order ---
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_TASKS_TABLE_COLUMN_ORDER)
        order_settings = {}
        for definition in column_definitions:
            pos = self.settings.settings.value(definition.id)
            if pos is not None:
                try:
                    order_settings[definition.column.value] = int(pos)
                except Exception:
                    print(f"[DEBUG] Invalid position for column '{definition.id}': {pos}")
        self.settings.end_group()

        # --- Apply visibility, widths, and order ---
        header = self.horizontalHeader()

        # First, set visibility and width for each column
        for definition in column_definitions:
            is_visible = visibility_settings.get(definition.id, True)
            width = width_settings.get(definition.id, definition.width)
            print(f"[DEBUG] Column '{definition.id}': visible={is_visible}, width={width}")
            self.setColumnHidden(definition.column.value, not is_visible)
            if width is not None:
                self.setColumnWidth(definition.column.value, max(width, 100))

        # Then, apply column order
        # Build a list of (logical_index, visual_position) for ALL columns (including hidden ones)
        all_columns = [
            (definition.column.value, order_settings.get(definition.column.value, idx))
            for idx, definition in enumerate(column_definitions)
        ]
        # Sort by saved visual position
        all_columns.sort(key=lambda x: x[1])

        # Move sections to match the saved order
        for target_visual, (logical_index, _) in enumerate(all_columns):
            current_visual = header.visualIndex(logical_index)
            if current_visual != target_visual:
                print(f"[DEBUG] Moving column logical_index={logical_index} from visual={current_visual} to visual={target_visual}")
                header.moveSection(current_visual, target_visual)

        print("[DEBUG] reload_column_order_from_settings() finished")
        

    def copy_selected_fields(self):
        selected_text = ""
        for row in self.selectionModel().selectedRows():
            row_index = row.row()
            file_name = self.model().data(self.model().index(row_index, Column.FILE.value))
            url = self.model().data(self.model().index(row_index, Column.URL.value))

            selected_text += f"{file_name}{url}\n"

        selected_text = selected_text.rstrip("\n")
        QApplication.clipboard().setText(selected_text)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Return:
            self.return_clicked.emit()

        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected_fields()
            return

        super().keyPressEvent(event)

    def selected_transcriptions(self) -> List[Transcription]:
        selected = self.selectionModel().selectedRows()
        return [self.transcription(row) for row in selected]

    def delete_transcriptions(self, rows: List[QModelIndex]):
        for row in rows:
            self.model().removeRow(row.row())
        self.model().submitAll()

    def transcription(self, index: QModelIndex) -> Transcription:
        return Transcription.from_record(self.model().record(index.row()))

    def refresh_all(self):
        self.model().select()

    def refresh_row(self, id: UUID):
        for i in range(self.model().rowCount()):
            record = self.model().record(i)
            if record.value("id") == str(id):
                self.model().selectRow(i)
                return

    @staticmethod
    def format_timedelta(delta: timedelta):
        mm, ss = divmod(delta.seconds, 60)
        result = f"{ss}s"
        if mm == 0:
            return result
        hh, mm = divmod(mm, 60)
        result = f"{mm}m {result}"
        if hh == 0:
            return result
        return f"{hh}h {result}"

    def on_rename_action(self):
        selected_rows = self.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # Get the first selected transcription
        transcription = self.transcription(selected_rows[0])
        
        # Get current name or fallback to file name
        current_name = transcription.name or (
            transcription.url if transcription.url 
            else os.path.basename(transcription.file) if transcription.file 
            else ""
        )
        
        # Show input dialog
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, 
            _("Rename Transcription"), 
            _("Enter new name:"), 
            text=current_name
        )
        
        if ok and new_name.strip():
            # Update the transcription name
            from uuid import UUID
            self.transcription_service.update_transcription_name(
                UUID(transcription.id), 
                new_name.strip()
            )
            self.refresh_all()

    def on_notes_action(self):
        selected_rows = self.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # Get the first selected transcription
        transcription = self.transcription(selected_rows[0])
        
        # Show input dialog for notes
        from PyQt6.QtWidgets import QInputDialog
        current_notes = transcription.notes or ""
        new_notes, ok = QInputDialog.getMultiLineText(
            self, 
            _("Edit Notes"), 
            _("Enter notes for this transcription:"), 
            text=current_notes
        )
        
        if ok:
            # Update the transcription notes
            from uuid import UUID
            self.transcription_service.update_transcription_notes(
                UUID(transcription.id), 
                new_notes
            )
            self.refresh_all()

    def on_restart_transcription_action(self):
        """Restart transcription for failed or canceled tasks"""
        selected_rows = self.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # Get the first selected transcription
        transcription = self.transcription(selected_rows[0])
        
        # Check if the task can be restarted
        if transcription.status not in ["failed", "canceled"]:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, 
                _("Cannot Restart"), 
                _("Only failed or canceled transcriptions can be restarted.")
            )
            return
        
        # Reset the transcription status to queued by directly updating the database
        from uuid import UUID
        from buzz.transcriber.transcriber import FileTranscriptionTask
        
        # Use a direct database update to reset status
        query = self.transcription_service.transcription_dao._create_query()
        query.prepare(
            """
            UPDATE transcription
            SET status = :status, progress = :progress, time_started = NULL, time_ended = NULL, error_message = NULL
            WHERE id = :id
        """
        )
        
        query.bindValue(":id", str(transcription.id))
        query.bindValue(":status", FileTranscriptionTask.Status.QUEUED.value)
        query.bindValue(":progress", 0.0)
        
        if query.exec():
            # Create a new FileTranscriptionTask from the database record
            # and add it to the queue worker
            self._restart_transcription_task(transcription)
            
            # Refresh the table to show updated status
            self.refresh_all()
        else:
            # Show error if update failed
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 
                _("Error"), 
                _("Failed to restart transcription: {}").format(query.lastError().text())
            )
    
    def _restart_transcription_task(self, transcription):
        """Create a new FileTranscriptionTask and add it to the queue worker"""
        from buzz.transcriber.transcriber import (
            FileTranscriptionTask, 
            TranscriptionOptions, 
            FileTranscriptionOptions,
            Task
        )
        from buzz.model_loader import TranscriptionModel, ModelType
        from buzz.transcriber.transcriber import OutputFormat
        
        # Recreate the transcription options from the database record
        from buzz.model_loader import WhisperModelSize
        
        # Convert string whisper_model_size to enum if it exists
        whisper_model_size = None
        if transcription.whisper_model_size:
            try:
                whisper_model_size = WhisperModelSize(transcription.whisper_model_size)
            except ValueError:
                # If the stored value is invalid, use a default
                whisper_model_size = WhisperModelSize.TINY
        
        transcription_options = TranscriptionOptions(
            language=transcription.language if transcription.language else None,
            task=Task(transcription.task) if transcription.task else Task.TRANSCRIBE,
            model=TranscriptionModel(
                model_type=ModelType(transcription.model_type) if transcription.model_type else ModelType.WHISPER,
                whisper_model_size=whisper_model_size,
                hugging_face_model_id=transcription.hugging_face_model_id
            ),
            word_level_timings=transcription.word_level_timings == "1" if transcription.word_level_timings else False,
            extract_speech=transcription.extract_speech == "1" if transcription.extract_speech else False,
            initial_prompt="",  # Not stored in database, use default
            openai_access_token="",  # Not stored in database, use default
            enable_llm_translation=False,  # Not stored in database, use default
            llm_prompt="",  # Not stored in database, use default
            llm_model=""  # Not stored in database, use default
        )
        
        # Recreate the file transcription options
        output_formats = set()
        if transcription.export_formats:
            for format_str in transcription.export_formats.split(','):
                try:
                    output_formats.add(OutputFormat(format_str.strip()))
                except ValueError:
                    pass  # Skip invalid formats
        
        file_transcription_options = FileTranscriptionOptions(
            url=transcription.url if transcription.url else None,
            output_formats=output_formats
        )
        
        # Get the model path from the transcription options
        model_path = transcription_options.model.get_local_model_path()
        if model_path is None:
            # If model is not available locally, we need to download it
            from buzz.model_loader import ModelDownloader
            ModelDownloader(model=transcription_options.model).run()
            model_path = transcription_options.model.get_local_model_path()
        
        if model_path is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 
                _("Error"), 
                _("Could not restart transcription: model not available and could not be downloaded.")
            )
            return
        
        # Create the new task
        task = FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=file_transcription_options,
            model_path=model_path,
            file_path=transcription.file if transcription.file else None,
            url=transcription.url if transcription.url else None,
            output_directory=transcription.output_folder if transcription.output_folder else None,
            source=FileTranscriptionTask.Source(transcription.source) if transcription.source else FileTranscriptionTask.Source.FILE_IMPORT,
            uid=UUID(transcription.id)
        )
        
        # Add the task to the queue worker
        # We need to access the main window's transcriber worker
        # This is a bit of a hack, but it's the cleanest way given the current architecture
        main_window = self.parent()
        while main_window and not hasattr(main_window, 'transcriber_worker'):
            main_window = main_window.parent()
        
        if main_window and hasattr(main_window, 'transcriber_worker'):
            main_window.transcriber_worker.add_task(task)
        else:
            # Fallback: show error if we can't find the transcriber worker
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 
                _("Error"), 
                _("Could not restart transcription: transcriber worker not found.")
            )