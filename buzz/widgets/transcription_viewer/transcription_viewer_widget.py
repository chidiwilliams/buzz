import logging
from typing import Optional
from uuid import UUID

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QShowEvent, QTextCursor, QColor
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtSql import QSqlRecord
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QToolButton,
    QLabel,
    QMessageBox,
    QLineEdit,
    QPushButton,
    QFrame,
    QCheckBox,
    QAbstractItemView,
    QComboBox,
)

from buzz.locale import _
from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.paths import file_path_as_title
from buzz.settings.shortcuts import Shortcuts
from buzz.settings.shortcut import Shortcut
from buzz.settings.settings import Settings
from buzz.store.keyring_store import get_password, Key
from buzz.widgets.audio_player import AudioPlayer
from buzz.widgets.icon import (
    FileDownloadIcon,
    TranslateIcon,
    ResizeIcon,
    ScrollToCurrentIcon,
)
from buzz.translator import Translator
from buzz.widgets.text_display_box import TextDisplayBox
from buzz.widgets.toolbar import ToolBar
from buzz.transcriber.transcriber import TranscriptionOptions, Segment
from buzz.widgets.transcriber.advanced_settings_dialog import AdvancedSettingsDialog
from buzz.widgets.transcription_viewer.export_transcription_menu import (
    ExportTranscriptionMenu,
)
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    TranscriptionSegmentsEditorWidget,
)
from buzz.widgets.transcription_viewer.transcription_view_mode_tool_button import (
    TranscriptionViewModeToolButton,
    ViewMode
)
from buzz.widgets.transcription_viewer.transcription_resizer_widget import TranscriptionResizerWidget


class TranscriptionViewerWidget(QWidget):
    resize_button_clicked = pyqtSignal()
    transcription: Transcription
    settings = Settings()

    def __init__(
        self,
        transcription: Transcription,
        transcription_service: TranscriptionService,
        shortcuts: Shortcuts,
        parent: Optional["QWidget"] = None,
        flags: Qt.WindowType = Qt.WindowType.Widget,
        transcriptions_updated_signal: Optional[pyqtSignal] = None,
    ) -> None:
        super().__init__(parent, flags)
        self.transcription = transcription
        self.transcription_service = transcription_service
        self.shortcuts = shortcuts

        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        self.setWindowTitle(file_path_as_title(transcription.file))

        self.transcription_resizer_dialog = None
        self.transcriptions_updated_signal = transcriptions_updated_signal

        self.translation_thread = None
        self.translator = None
        self.view_mode = ViewMode.TIMESTAMPS

        # Search functionality
        self.search_text = ""
        self.current_search_index = 0
        self.search_results = []

        # Loop functionality
        self.segment_looping_enabled = self.settings.settings.value("transcription_viewer/segment_looping_enabled", True, type=bool)

        # Currently selected segment for loop functionality
        self.currently_selected_segment = None

        # Can't reuse this globally, as transcripts may get translated, so need to get them each time
        segments = self.transcription_service.get_transcription_segments(
            transcription_id=self.transcription.id_as_uuid
        )
        self.has_translations = any(segment.translation.strip() for segment in segments)

        self.openai_access_token = get_password(Key.OPENAI_API_KEY)

        preferences = self.load_preferences()

        (
            self.transcription_options,
            self.file_transcription_options,
        ) = preferences.to_transcription_options(
            openai_access_token=self.openai_access_token,
        )

        self.transcription_options_dialog = AdvancedSettingsDialog(
            transcription_options=self.transcription_options, parent=self
        )
        self.transcription_options_dialog.transcription_options_changed.connect(
            self.on_transcription_options_changed
        )

        self.translator = Translator(
            self.transcription_options,
            self.transcription_options_dialog,
        )

        self.translation_thread = QThread()
        self.translator.moveToThread(self.translation_thread)

        self.translation_thread.started.connect(self.translator.start)

        self.translation_thread.start()

        self.table_widget = TranscriptionSegmentsEditorWidget(
            transcription_id=UUID(hex=transcription.id),
            translator=self.translator,

            parent=self
        )
        self.table_widget.segment_selected.connect(self.on_segment_selected)

        self.text_display_box = TextDisplayBox(self)
        font = QFont(self.text_display_box.font().family(), 14)
        self.text_display_box.setFont(font)

        self.audio_player = AudioPlayer(file_path=transcription.file)
        self.audio_player.position_ms_changed.connect(
            self.on_audio_player_position_ms_changed
        )

        self.current_segment_label = QLabel("", self)
        self.current_segment_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.current_segment_label.setContentsMargins(0, 0, 0, 10)
        self.current_segment_label.setWordWrap(True)

        font_metrics = self.current_segment_label.fontMetrics()
        max_height = font_metrics.lineSpacing() * 3
        self.current_segment_label.setMaximumHeight(max_height)

        layout = QVBoxLayout(self)

        toolbar = ToolBar(self)

        view_mode_tool_button = TranscriptionViewModeToolButton(
            shortcuts,
            self.has_translations,
            self.translator.translation,
        )
        view_mode_tool_button.view_mode_changed.connect(self.on_view_mode_changed)
        toolbar.addWidget(view_mode_tool_button)

        export_tool_button = QToolButton()
        export_tool_button.setText(_("Export"))
        export_tool_button.setIcon(FileDownloadIcon(self))
        export_tool_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )

        export_transcription_menu = ExportTranscriptionMenu(
            transcription,
            transcription_service,
            self.has_translations,
            self.translator.translation,
            self
        )
        export_tool_button.setMenu(export_transcription_menu)
        export_tool_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(export_tool_button)

        translate_button = QToolButton()
        translate_button.setText(_("Translate"))
        translate_button.setIcon(TranslateIcon(self))
        translate_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        translate_button.clicked.connect(self.on_translate_button_clicked)

        toolbar.addWidget(translate_button)

        resize_button = QToolButton()
        resize_button.setText(_("Resize"))
        resize_button.setObjectName("resize_button")
        resize_button.setIcon(ResizeIcon(self))
        resize_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        resize_button.clicked.connect(self.on_resize_button_clicked)

        toolbar.addWidget(resize_button)

        # Add scroll to current text button
        self.scroll_to_current_button = QToolButton()
        self.scroll_to_current_button.setText(_("Scroll to Current"))
        self.scroll_to_current_button.setIcon(ScrollToCurrentIcon(self))
        self.scroll_to_current_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.scroll_to_current_button.setToolTip(_("Scroll to the currently spoken text"))
        self.scroll_to_current_button.clicked.connect(self.on_scroll_to_current_button_clicked)
        toolbar.addWidget(self.scroll_to_current_button)

        layout.setMenuBar(toolbar)

        # Search bar
        self.create_search_bar()
        layout.addWidget(self.search_frame)

        layout.addWidget(self.table_widget)
        layout.addWidget(self.text_display_box)
        
        # Loop controls section - positioned between text display and audio player
        self.create_loop_controls()
        layout.addWidget(self.loop_controls_frame)
        
        layout.addWidget(self.audio_player)
        layout.addWidget(self.current_segment_label)

        self.setLayout(layout)

        # Set up keyboard shortcuts
        self.setup_shortcuts()

        self.reset_view()

    def create_search_bar(self):
        """Create the search bar widget"""
        self.search_frame = QFrame()
        self.search_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        self.search_frame.setMaximumHeight(60)
        
        search_layout = QHBoxLayout(self.search_frame)
        search_layout.setContentsMargins(10, 5, 10, 5)
        
        # Search label
        search_label = QLabel(_("Search:"))
        search_label.setStyleSheet("font-weight: bold;")
        search_layout.addWidget(search_label)
        
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_("Enter text to search..."))
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.search_next)
        self.search_input.setMinimumWidth(200)
        
        # Add keyboard shortcuts for search navigation
        from PyQt6.QtGui import QKeySequence
        self.search_input.installEventFilter(self)
        
        # Add search status indicator
        self.search_status_label = QLabel("")
        self.search_status_label.setStyleSheet("color: #666; font-size: 10px;")
        self.search_status_label.setMaximumWidth(80)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_status_label)
        
        # Search buttons
        self.search_prev_button = QPushButton(_("↑"))
        self.search_prev_button.setToolTip(_("Previous match (Shift+Enter)"))
        self.search_prev_button.clicked.connect(self.search_previous)
        self.search_prev_button.setEnabled(False)
        self.search_prev_button.setMaximumWidth(40)
        search_layout.addWidget(self.search_prev_button)
        
        self.search_next_button = QPushButton(_("↓"))
        self.search_next_button.setToolTip(_("Next match (Enter)"))
        self.search_next_button.clicked.connect(self.search_next)
        self.search_next_button.setEnabled(False)
        self.search_next_button.setMaximumWidth(40)
        search_layout.addWidget(self.search_next_button)
        
        # Clear button
        self.clear_search_button = QPushButton(_("Clear"))
        self.clear_search_button.clicked.connect(self.clear_search)
        self.clear_search_button.setMaximumWidth(60)
        search_layout.addWidget(self.clear_search_button)
        
        # Close button
        self.close_search_button = QPushButton(_("×"))
        self.close_search_button.setToolTip(_("Close search"))
        self.close_search_button.clicked.connect(self.hide_search_bar)
        self.close_search_button.setMaximumWidth(30)
        self.close_search_button.setStyleSheet("font-weight: bold; font-size: 14px;")
        search_layout.addWidget(self.close_search_button)
        
        # Results label
        self.search_results_label = QLabel("")
        self.search_results_label.setStyleSheet("color: #666; font-size: 11px;")
        search_layout.addWidget(self.search_results_label)
        
        search_layout.addStretch()
        
        # Initially hide the search bar
        self.search_frame.hide()

    def create_loop_controls(self):
        """Create the loop controls widget"""
        self.loop_controls_frame = QFrame()
        self.loop_controls_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        self.loop_controls_frame.setMaximumHeight(50)
        
        loop_layout = QHBoxLayout(self.loop_controls_frame)
        loop_layout.setContentsMargins(10, 5, 10, 5)
        
        # Loop controls label
        loop_label = QLabel(_("Playback Controls:"))
        loop_label.setStyleSheet("font-weight: bold;")
        loop_layout.addWidget(loop_label)
        
        # Loop toggle button
        self.loop_toggle = QCheckBox(_("Loop Segment"))
        self.loop_toggle.setChecked(self.segment_looping_enabled)
        self.loop_toggle.setToolTip(_("Enable/disable looping when clicking on transcript segments"))
        self.loop_toggle.toggled.connect(self.on_loop_toggle_changed)
        loop_layout.addWidget(self.loop_toggle)
        
        # Follow audio toggle button
        self.follow_audio_enabled = self.settings.settings.value("transcription_viewer/follow_audio_enabled", False, type=bool)
        self.follow_audio_toggle = QCheckBox(_("Follow Audio"))
        self.follow_audio_toggle.setChecked(self.follow_audio_enabled)
        self.follow_audio_toggle.setToolTip(_("Enable/disable following the current audio position in the transcript. When enabled, automatically scrolls to current text."))
        self.follow_audio_toggle.toggled.connect(self.on_follow_audio_toggle_changed)
        loop_layout.addWidget(self.follow_audio_toggle)
        
        # Visual separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.VLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)
        separator1.setMaximumHeight(20)
        loop_layout.addWidget(separator1)
        
        # Speed controls
        speed_label = QLabel("Speed:")
        speed_label.setStyleSheet("font-weight: bold;")
        loop_layout.addWidget(speed_label)
        
        self.speed_combo = QComboBox()
        self.speed_combo.setEditable(True)
        self.speed_combo.addItems(["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"])
        self.speed_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.speed_combo.currentTextChanged.connect(self.on_speed_changed)
        self.speed_combo.setMaximumWidth(80)
        loop_layout.addWidget(self.speed_combo)
        
        self.speed_down_btn = QPushButton("-")
        self.speed_down_btn.setMaximumWidth(25)
        self.speed_down_btn.setMaximumHeight(25)
        self.speed_down_btn.clicked.connect(self.decrease_speed)
        loop_layout.addWidget(self.speed_down_btn)
        
        self.speed_up_btn = QPushButton("+")
        self.speed_up_btn.setMaximumWidth(25)
        self.speed_up_btn.setMaximumHeight(25)
        self.speed_up_btn.clicked.connect(self.increase_speed)
        loop_layout.addWidget(self.speed_up_btn)
        
        # Initialize speed control with current value from audio player
        self.initialize_speed_control()
        
        loop_layout.addStretch()

    def initialize_speed_control(self):
        """Initialize the speed control with current value from audio player"""
        try:
            # Get current speed from audio player
            current_speed = self.audio_player.media_player.playbackRate()
            # Ensure it's within valid range
            current_speed = max(0.1, min(5.0, current_speed))
            # Set the combo box text
            speed_text = f"{current_speed:.2f}x"
            self.speed_combo.setCurrentText(speed_text)
        except Exception as e:
            logging.warning(f"Could not initialize speed control: {e}")
            # Default to 1.0x
            self.speed_combo.setCurrentText("1.0x")

    def on_speed_changed(self, speed_text: str):
        """Handle speed change from the combo box"""
        try:
            # Extract the numeric value from speed text (e.g., "1.5x" -> 1.5)
            clean_text = speed_text.replace('x', '').strip()
            speed_value = float(clean_text)
            
            # Clamp the speed value to valid range
            speed_value = max(0.1, min(5.0, speed_value))
            
            # Update the combo box text to show the clamped value
            if not speed_text.endswith('x'):
                speed_text = f"{speed_value:.2f}x"
            
            # Block signals to prevent recursion
            self.speed_combo.blockSignals(True)
            self.speed_combo.setCurrentText(speed_text)
            self.speed_combo.blockSignals(False)
            
            # Set the playback rate on the audio player
            self.audio_player.media_player.setPlaybackRate(speed_value)
            
            # Save the new rate to settings
            self.settings.set_value(self.settings.Key.AUDIO_PLAYBACK_RATE, speed_value)
            
        except ValueError:
            logging.warning(f"Invalid speed value: {speed_text}")
            # Reset to current valid value
            current_text = self.speed_combo.currentText()
            if current_text != speed_text:
                self.speed_combo.setCurrentText(current_text)

    def increase_speed(self):
        """Increase speed by 0.05"""
        current_speed = self.get_current_speed()
        new_speed = min(5.0, current_speed + 0.05)
        self.set_speed(new_speed)

    def decrease_speed(self):
        """Decrease speed by 0.05"""
        current_speed = self.get_current_speed()
        new_speed = max(0.1, current_speed - 0.05)
        self.set_speed(new_speed)

    def get_current_speed(self) -> float:
        """Get the current playback speed as a float"""
        try:
            speed_text = self.speed_combo.currentText()
            return float(speed_text.replace('x', ''))
        except ValueError:
            return 1.0

    def set_speed(self, speed: float):
        """Set the playback speed programmatically"""
        # Clamp the speed value to valid range
        speed = max(0.1, min(5.0, speed))
        
        # Update the combo box
        speed_text = f"{speed:.2f}x"
        self.speed_combo.setCurrentText(speed_text)
        
        # Set the playback rate on the audio player
        self.audio_player.media_player.setPlaybackRate(speed)
        
        # Save the new rate to settings
        self.settings.set_value(self.settings.Key.AUDIO_PLAYBACK_RATE, speed)

    def on_search_text_changed(self, text: str):
        """Handle search text changes"""
        self.search_text = text.strip()
        if self.search_text:
            # Add a small delay to avoid searching on every keystroke for long text
            if len(self.search_text) >= 2:
                self.search_status_label.setText(_("Searching..."))
                self.perform_search()
            self.search_frame.show()
        else:
            self.clear_search()
            # Don't hide the search frame immediately, let user clear it manually

    def perform_search(self):
        """Perform the actual search based on current view mode"""
        self.search_results = []
        self.current_search_index = 0
        
        if self.view_mode == ViewMode.TIMESTAMPS:
            self.search_in_table()
        else:  # TEXT or TRANSLATION mode
            self.search_in_text()
        
        self.update_search_ui()

    def search_in_table(self):
        """Search in the table view (segments)"""
        segments = self.table_widget.segments()
        search_text_lower = self.search_text.lower()
        
        # Limit search results to avoid performance issues with very long segments
        max_results = 100
        
        for i, segment in enumerate(segments):
            if len(self.search_results) >= max_results:
                break
                
            text = segment.value("text").lower()
            if search_text_lower in text:
                self.search_results.append(("table", i, segment))
        
        # Also search in translations if available
        if self.has_translations:
            for i, segment in enumerate(segments):
                if len(self.search_results) >= max_results:
                    break
                    
                translation = segment.value("translation").lower()
                if search_text_lower in translation:
                    self.search_results.append(("table", i, segment))
        
        if len(self.search_results) >= max_results:
            self.search_results_label.setText(f"{max_results}+ matches (showing first {max_results})")

    def search_in_text(self):
        """Search in the text display box"""
        text = self.text_display_box.toPlainText()
        search_text_lower = self.search_text.lower()
        text_lower = text.lower()
        
        # Limit search results to avoid performance issues with very long text
        max_results = 100
        
        start = 0
        result_count = 0
        while True:
            pos = text_lower.find(search_text_lower, start)
            if pos == -1 or result_count >= max_results:
                break
            self.search_results.append(("text", pos, pos + len(self.search_text)))
            start = pos + 1
            result_count += 1
        
        if result_count >= max_results:
            self.search_results_label.setText(f"{max_results}+ matches (showing first {max_results})")

    def update_search_ui(self):
        """Update the search UI elements"""
        if self.search_results:
            self.search_results_label.setText(f"{len(self.search_results)} matches")
            self.search_prev_button.setEnabled(True)
            self.search_next_button.setEnabled(True)
            self.highlight_current_match()
            self.search_status_label.setText(_("Ready"))
        else:
            self.search_results_label.setText(_("No matches found"))
            self.search_prev_button.setEnabled(False)
            self.search_next_button.setEnabled(False)
            self.search_status_label.setText(_("No results"))

    def highlight_current_match(self):
        """Highlight the current search match"""
        if not self.search_results:
            return
            
        match_type, match_data, _ = self.search_results[self.current_search_index]
        
        if match_type == "table":
            # Highlight in table
            self.highlight_table_match(match_data)
        else:  # text
            # Highlight in text display
            self.highlight_text_match(match_data)

    def highlight_table_match(self, row_index: int):
        """Highlight a match in the table view"""
        # Select the row containing the match
        self.table_widget.selectRow(row_index)
        # Scroll to the row
        self.table_widget.scrollTo(self.table_widget.model().index(row_index, 0))

    def highlight_text_match(self, start_pos: int):
        """Highlight a match in the text display"""
        cursor = QTextCursor(self.text_display_box.document())
        cursor.setPosition(start_pos)
        cursor.setPosition(start_pos + len(self.search_text), QTextCursor.MoveMode.KeepAnchor)
        
        # Set the cursor to highlight the text
        self.text_display_box.setTextCursor(cursor)
        
        # Ensure the highlighted text is visible
        self.text_display_box.ensureCursorVisible()

    def search_next(self):
        """Go to next search result"""
        if not self.search_results:
            return
            
        self.current_search_index = (self.current_search_index + 1) % len(self.search_results)
        self.highlight_current_match()
        self.update_search_results_label()

    def search_previous(self):
        """Go to previous search result"""
        if not self.search_results:
            return
            
        self.current_search_index = (self.current_search_index - 1) % len(self.search_results)
        self.highlight_current_match()
        self.update_search_results_label()

    def update_search_results_label(self):
        """Update the search results label with current position"""
        if self.search_results:
            self.search_results_label.setText(f"{self.current_search_index + 1} of {len(self.search_results)} matches")

    def clear_search(self):
        """Clear the search and reset highlighting"""
        self.search_text = ""
        self.search_results = []
        self.current_search_index = 0
        self.search_input.clear()
        self.search_results_label.setText("")
        self.search_status_label.setText("")
        self.search_prev_button.setEnabled(False)
        self.search_next_button.setEnabled(False)
        
        # Clear text highlighting
        if self.view_mode in (ViewMode.TEXT, ViewMode.TRANSLATION):
            cursor = QTextCursor(self.text_display_box.document())
            cursor.clearSelection()
            self.text_display_box.setTextCursor(cursor)
        
        # Keep search bar visible but clear the input
        self.search_input.setFocus()

    def hide_search_bar(self):
        """Hide the search bar completely"""
        self.search_frame.hide()
        self.clear_search()
        self.search_input.clearFocus()

    def setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        from PyQt6.QtGui import QShortcut, QKeySequence
        
        # Search shortcut (Ctrl+F)
        search_shortcut = QShortcut(QKeySequence(self.shortcuts.get(Shortcut.SEARCH_TRANSCRIPT)), self)
        search_shortcut.activated.connect(self.focus_search_input)
        
        # Scroll to current text shortcut (Ctrl+G)
        scroll_to_current_shortcut = QShortcut(QKeySequence(self.shortcuts.get(Shortcut.SCROLL_TO_CURRENT_TEXT)), self)
        scroll_to_current_shortcut.activated.connect(self.on_scroll_to_current_button_clicked)

    def focus_search_input(self):
        """Focus the search input field"""
        self.search_frame.show()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def eventFilter(self, obj, event):
        """Event filter to handle keyboard shortcuts in search input"""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        
        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            # The event is already a QKeyEvent, no need to create a new one
            if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                self.search_previous()
                return True
            elif event.key() == Qt.Key.Key_Escape:
                self.hide_search_bar()
                return True
        return super().eventFilter(obj, event)

    def reset_view(self):
        if self.view_mode == ViewMode.TIMESTAMPS:
            self.text_display_box.hide()
            self.table_widget.show()
            self.audio_player.show()
        elif self.view_mode == ViewMode.TEXT:
            segments = self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )

            combined_text = ""
            previous_end_time = None

            for segment in segments:
                if previous_end_time is not None and (segment.start_time - previous_end_time) >= 2000:
                    combined_text += "\n\n"
                combined_text += segment.text.strip() + " "
                previous_end_time = segment.end_time

            self.text_display_box.setPlainText(combined_text.strip())
            self.text_display_box.show()
            self.table_widget.hide()
            self.audio_player.hide()
        else: # ViewMode.TRANSLATION
            segments = self.transcription_service.get_transcription_segments(
                transcription_id=self.transcription.id_as_uuid
            )
            self.text_display_box.setPlainText(
                " ".join(segment.translation.strip() for segment in segments)
            )
            self.text_display_box.show()
            self.table_widget.hide()
            self.audio_player.hide()
        
        # Refresh search if there's active search text
        if self.search_text:
            self.perform_search()

    def on_view_mode_changed(self, view_mode: ViewMode) -> None:
        self.view_mode = view_mode
        self.reset_view()
        
        # Refresh search if there's active search text
        if self.search_text:
            self.perform_search()

    def on_segment_selected(self, segment: QSqlRecord):
        # Store the currently selected segment for loop functionality
        self.currently_selected_segment = segment
        
        # Get current audio position for timestamp
        current_pos = self.audio_player.position_ms
        
        if self.segment_looping_enabled:
            # Check if we're currently in an active loop
            current_range = self.audio_player.range_ms
            
            # Set range for looping behavior (regardless of playback state)
            start_time = segment.value("start_time")
            end_time = segment.value("end_time")
            self.audio_player.set_range((start_time, end_time))
            
            # Reset looping flag to ensure new loops work
            self.audio_player.is_looping = False
        else:
            # Always seek to the clicked segment start time
            start_time = segment.value("start_time")
            self.audio_player.set_position(start_time)
            
            # Always highlight the clicked segment
            segments = self.table_widget.segments()
            for i, seg in enumerate(segments):
                if seg.value("id") == segment.value("id"):
                    self.table_widget.highlight_and_scroll_to_row(i)
                    break

    def on_audio_player_position_ms_changed(self, position_ms: int) -> None:
        segments = self.table_widget.segments()
        current_segment = next(
            (
                segment
                for segment in segments
                if segment.value("start_time")
                <= position_ms
                < segment.value("end_time")
            ),
            None,
        )
        if current_segment is not None:
            self.current_segment_label.setText(current_segment.value("text"))
            
            # Update highlighting based on follow audio and loop settings
            if self.follow_audio_enabled:
                # Follow audio mode: highlight the current segment based on audio position
                if not self.segment_looping_enabled or self.currently_selected_segment is None:
                    # Normal mode: highlight the current segment
                    for i, segment in enumerate(segments):
                        if segment.value("id") == current_segment.value("id"):
                            self.table_widget.highlight_and_scroll_to_row(i)
                            break
                else:
                    # Loop mode: only highlight if we're in a different segment than the selected one
                    if current_segment.value("id") != self.currently_selected_segment.value("id"):
                        for i, segment in enumerate(segments):
                            if segment.value("id") == current_segment.value("id"):
                                self.table_widget.highlight_and_scroll_to_row(i)
                                break
            else:
                # Don't follow audio: keep highlighting on the selected segment
                if self.currently_selected_segment is not None:
                    # Find and highlight the selected segment
                    for i, segment in enumerate(segments):
                        if segment.value("id") == self.currently_selected_segment.value("id"):
                            self.table_widget.highlight_and_scroll_to_row(i)
                            break
                # Don't do any highlighting if no segment is selected and follow is disabled

    def load_preferences(self):
        self.settings.settings.beginGroup("file_transcriber")
        preferences = FileTranscriptionPreferences.load(settings=self.settings.settings)
        self.settings.settings.endGroup()
        return preferences

    def open_advanced_settings(self):
        self.transcription_options_dialog.show()

    def on_transcription_options_changed(
            self, transcription_options: TranscriptionOptions
    ):
        self.transcription_options = transcription_options

    def on_translate_button_clicked(self):
        if len(self.openai_access_token) == 0:
            QMessageBox.information(
                self,
                _("API Key Required"),
                _("Please enter OpenAI API Key in preferences")
            )

            return

        if self.transcription_options.llm_model == "" or self.transcription_options.llm_prompt == "":
            self.transcription_options_dialog.accepted.connect(self.run_translation)
            self.transcription_options_dialog.show()
            return

        self.run_translation()

    def run_translation(self):
        if self.transcription_options.llm_model == "" or self.transcription_options.llm_prompt == "":
            return

        segments = self.table_widget.segments()
        for segment in segments:
            self.translator.enqueue(segment.value("text"), segment.value("id"))

    def on_resize_button_clicked(self):
        self.transcription_resizer_dialog = TranscriptionResizerWidget(
            transcription=self.transcription,
            transcription_service=self.transcription_service,
            transcriptions_updated_signal=self.transcriptions_updated_signal,
        )

        self.transcriptions_updated_signal.connect(self.close)

        self.transcription_resizer_dialog.show()

    def on_loop_toggle_changed(self, enabled: bool):
        """Handle loop toggle state change"""
        self.segment_looping_enabled = enabled
        # Save preference to settings
        self.settings.settings.setValue("transcription_viewer/segment_looping_enabled", enabled)
        
        if enabled:
            # If looping is re-enabled and we have a selected segment, return to it
            if self.currently_selected_segment is not None:
                # Find the row index of the selected segment
                segments = self.table_widget.segments()
                for i, segment in enumerate(segments):
                    if segment.value("id") == self.currently_selected_segment.value("id"):
                        # Highlight and scroll to the selected segment
                        self.table_widget.highlight_and_scroll_to_row(i)
                        
                        # Get the segment timing
                        start_time = self.currently_selected_segment.value("start_time")
                        end_time = self.currently_selected_segment.value("end_time")
                        
                        # Set the loop range for the selected segment
                        self.audio_player.set_range((start_time, end_time))
                        
                        # If audio is currently playing and outside the range, jump to the start
                        current_pos = self.audio_player.position_ms
                        playback_state = self.audio_player.media_player.playbackState()
                        if (playback_state == QMediaPlayer.PlaybackState.PlayingState and 
                            (current_pos < start_time or current_pos > end_time)):
                            self.audio_player.set_position(start_time)
                        
                        break
        else:
            # Clear any existing range if looping is disabled
            self.audio_player.clear_range()

    def on_follow_audio_toggle_changed(self, enabled: bool):
        """Handle follow audio toggle state change"""
        self.follow_audio_enabled = enabled
        # Save preference to settings
        self.settings.settings.setValue("transcription_viewer/follow_audio_enabled", enabled)
        
        if enabled:
            # When follow audio is first enabled, automatically scroll to current position
            # This gives immediate feedback that the feature is working
            self._auto_scroll_to_current_position()
        else:
            # If we have a selected segment, highlight it and keep it highlighted
            if self.currently_selected_segment is not None:
                segments = self.table_widget.segments()
                for i, segment in enumerate(segments):
                    if segment.value("id") == self.currently_selected_segment.value("id"):
                        self.table_widget.highlight_and_scroll_to_row(i)
                        break

    def on_scroll_to_current_button_clicked(self):
        """Handle scroll to current text button click"""
        current_pos = self.audio_player.position_ms
        segments = self.table_widget.segments()
        
        # Find the current segment based on audio position
        current_segment = next(
            (segment for segment in segments 
             if segment.value("start_time") <= current_pos < segment.value("end_time")),
            None
        )
        
        if current_segment is not None:
            # Find the row index and scroll to it
            for i, segment in enumerate(segments):
                if segment.value("id") == current_segment.value("id"):
                    # Only scroll if we're in timestamps view mode (table is visible)
                    if self.view_mode == ViewMode.TIMESTAMPS:
                        # Method 1: Use the table widget's built-in scrolling method
                        self.table_widget.highlight_and_scroll_to_row(i)
                        
                        # Method 2: Force immediate scrolling to ensure visibility
                        self._force_scroll_to_row(i)
                        
                        # Method 3: Direct scroll bar manipulation as fallback
                        self._direct_scroll_to_row(i)
                    break
        else:
            pass  # No segment found at current position

    def _ensure_segment_visible(self, row_index: int):
        """
        Ensures the segment at the given row index is visible in the table widget.
        This is a workaround for QTableView's scrollTo not always working as expected.
        """
        try:
            # Get current scroll position
            scroll_area = self.table_widget.parent()
            if hasattr(scroll_area, 'verticalScrollBar'):
                scroll_bar = scroll_area.verticalScrollBar()
                current_scroll = scroll_bar.value()
            
            # Try to scroll to the row
            model_index = self.table_widget.model().index(row_index, 0)
            self.table_widget.scrollTo(model_index)
            
            # Check if it's now visible
            visible_rect = self.table_widget.viewport().rect()
            row_rect = self.table_widget.visualRect(model_index)
            is_visible = visible_rect.intersects(row_rect)
            
        except Exception as e:
            pass  # Silently handle any errors

    def _force_scroll_to_row(self, row_index: int):
        """
        Forces the table widget to scroll to the given row index.
        This is a fallback if _ensure_segment_visible doesn't work.
        """
        try:
            # Method 1: Try using the table widget's scrollTo method with different hints
            try:
                model_index = self.table_widget.model().index(row_index, 0)
                
                # Try different scroll hints for better positioning
                self.table_widget.scrollTo(model_index, QAbstractItemView.ScrollHint.PositionAtCenter)
                
                # Also try to ensure the row is visible
                self.table_widget.scrollTo(model_index, QAbstractItemView.ScrollHint.EnsureVisible)
                
            except Exception as e:
                pass
            
            # Method 2: Try to find the scroll area and force scroll
            try:
                # Look for scroll area in parent hierarchy
                parent = self.table_widget.parent()
                while parent is not None:
                    if hasattr(parent, 'verticalScrollBar'):
                        scroll_bar = parent.verticalScrollBar()
                        if scroll_bar is not None:
                            # Calculate approximate scroll position
                            row_height = self.table_widget.rowHeight(row_index)
                            target_scroll = max(0, (row_index * row_height) - 100)  # 100px offset from top
                            
                            scroll_bar.setValue(target_scroll)
                            break
                    parent = parent.parent()
            except Exception as e:
                pass
            
            # Method 3: Try using the table's own scroll bar if available
            try:
                if hasattr(self.table_widget, 'verticalScrollBar'):
                    scroll_bar = self.table_widget.verticalScrollBar()
                    if scroll_bar is not None:
                        # Calculate scroll position based on row index
                        row_height = self.table_widget.rowHeight(row_index)
                        target_scroll = max(0, (row_index * row_height) - 50)  # 50px offset from top
                        
                        scroll_bar.setValue(target_scroll)
            except Exception as e:
                pass
                
        except Exception as e:
            pass  # Silently handle any errors

    def _direct_scroll_to_row(self, row_index: int):
        """
        Directly manipulate the scroll bar to scroll to a specific row.
        This is a more aggressive approach that should work in most cases.
        """
        try:
            # Get the table widget's scroll bar
            scroll_bar = self.table_widget.verticalScrollBar()
            if scroll_bar is not None:
                # Calculate the target scroll position
                # Get the total height of rows above the target row
                total_height = 0
                for row in range(row_index):
                    total_height += self.table_widget.rowHeight(row)
                
                # Add some offset to center the row better
                target_scroll = max(0, total_height - 100)
                
                # Set the scroll position
                scroll_bar.setValue(target_scroll)
                
                # Also try to ensure the row is visible by scrolling a bit more if needed
                if scroll_bar.value() == target_scroll:
                    # Try scrolling to the row with a different approach
                    model_index = self.table_widget.model().index(row_index, 0)
                    self.table_widget.scrollTo(model_index, QAbstractItemView.ScrollHint.PositionAtTop)
                
        except Exception as e:
            pass  # Silently handle any errors

    def _auto_scroll_to_current_position(self):
        """
        Automatically scroll to the current audio position.
        This is used when follow audio is first enabled to give immediate feedback.
        """
        try:
            # Only scroll if we're in timestamps view mode (table is visible)
            if self.view_mode != ViewMode.TIMESTAMPS:
                return
            
            current_pos = self.audio_player.position_ms
            segments = self.table_widget.segments()
            
            # Find the current segment based on audio position
            current_segment = next(
                (segment for segment in segments 
                 if segment.value("start_time") <= current_pos < segment.value("end_time")),
                None
            )
            
            if current_segment is not None:
                # Find the row index and scroll to it
                for i, segment in enumerate(segments):
                    if segment.value("id") == current_segment.value("id"):
                        # Use all available scrolling methods to ensure visibility
                        # Method 1: Use the table widget's built-in scrolling method
                        self.table_widget.highlight_and_scroll_to_row(i)
                        
                        # Method 2: Force immediate scrolling to ensure visibility
                        self._force_scroll_to_row(i)
                        
                        # Method 3: Direct scroll bar manipulation as fallback
                        self._direct_scroll_to_row(i)
                        break
                
        except Exception as e:
            pass  # Silently handle any errors

    def closeEvent(self, event):
        self.hide()

        if self.transcription_resizer_dialog:
            self.transcription_resizer_dialog.close()

        self.translator.stop()
        self.translation_thread.quit()
        self.translation_thread.wait()

        super().closeEvent(event)
