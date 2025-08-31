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
    QScrollArea,
    QSizePolicy,
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
    VisibilityIcon,
    PlayIcon,
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
        self.segment_looping_enabled = self.settings.settings.value("transcription_viewer/segment_looping_enabled", False, type=bool)
        
        # UI visibility preferences
        self.playback_controls_visible = self.settings.settings.value("transcription_viewer/playback_controls_visible", False, type=bool)
        self.find_widget_visible = self.settings.settings.value("transcription_viewer/find_widget_visible", False, type=bool)

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

        self.audio_player = AudioPlayer(file_path=transcription.file)
        self.audio_player.position_ms_changed.connect(
            self.on_audio_player_position_ms_changed
        )
        # Connect to playback state changes to automatically show controls
        self.audio_player.media_player.playbackStateChanged.connect(
            self.on_audio_playback_state_changed
        )

        # Create a better current segment display that handles long text
        self.current_segment_frame = QFrame()
        self.current_segment_frame.setFrameStyle(QFrame.Shape.NoFrame)
        
        segment_layout = QVBoxLayout(self.current_segment_frame)
        segment_layout.setContentsMargins(4, 4, 4, 4)  # Minimal margins for clean appearance
        segment_layout.setSpacing(0)  # No spacing between elements
        
        # Text display - centered with scroll capability (no header label)
        self.current_segment_text = QLabel("")
        self.current_segment_text.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.current_segment_text.setWordWrap(True)
        self.current_segment_text.setStyleSheet("color: #666; line-height: 1.2; margin: 0; padding: 4px;")
        self.current_segment_text.setMinimumHeight(60)  # Ensure minimum height for text
        
        # Make it scrollable for long text
        self.current_segment_scroll_area = QScrollArea()
        self.current_segment_scroll_area.setWidget(self.current_segment_text)
        self.current_segment_scroll_area.setWidgetResizable(True)
        self.current_segment_scroll_area.setFrameStyle(QFrame.Shape.NoFrame)
        self.current_segment_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.current_segment_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.current_segment_scroll_area.setStyleSheet("QScrollBar:vertical { width: 12px; } QScrollBar::handle:vertical { background: #ccc; border-radius: 6px; }")
        
        # Ensure the text label can expand to show all content
        self.current_segment_text.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        
        # Add scroll area to layout (simplified single-widget layout)
        segment_layout.addWidget(self.current_segment_scroll_area)
        
        # Initially hide the frame until there's content
        self.current_segment_frame.hide()

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

        # Add Find button
        self.find_button = QToolButton()
        self.find_button.setText(_("Find"))
        self.find_button.setIcon(VisibilityIcon(self))  # Using visibility icon for search
        self.find_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.find_button.setToolTip(_("Show/Hide Search Bar (Ctrl+F)"))
        self.find_button.setCheckable(True)  # Make button checkable to show state
        self.find_button.setChecked(False)   # Initially unchecked (search hidden)
        self.find_button.clicked.connect(self.toggle_search_bar_visibility)
        toolbar.addWidget(self.find_button)

        layout.setMenuBar(toolbar)

        # Search bar
        self.create_search_bar()
        # Search frame (minimal space)
        layout.addWidget(self.search_frame, 0)  # Stretch factor 0 (minimal)

        # Table widget should take the majority of the space
        layout.addWidget(self.table_widget, 1)  # Stretch factor 1 (majority)
        
        # Loop controls section (minimal space)
        self.create_loop_controls()
        layout.addWidget(self.loop_controls_frame, 0)  # Stretch factor 0 (minimal)
        
        # Audio player (minimal space)
        layout.addWidget(self.audio_player, 0)  # Stretch factor 0 (minimal)
        
        # Text display box (minimal space)
        layout.addWidget(self.text_display_box, 0)  # Stretch factor 0 (minimal)

        # Add current segment display (minimal space)
        layout.addWidget(self.current_segment_frame, 1)  # Stretch factor 0 (minimal)

        # Initially hide the current segment frame until a segment is selected
        self.current_segment_frame.hide()

        self.setLayout(layout)

        # Set up keyboard shortcuts
        self.setup_shortcuts()

        # Restore UI state from settings
        self.restore_ui_state()
        
        # Restore geometry from settings
        self.load_geometry()

        self.reset_view()

    def restore_ui_state(self):
        """Restore UI state from settings"""
        # Restore playback controls visibility
        if self.playback_controls_visible:
            self.show_loop_controls()
        
        # Restore find widget visibility
        if self.find_widget_visible:
            self.show_search_bar()

    def create_search_bar(self):
        """Create the search bar widget"""
        self.search_frame = QFrame()
        self.search_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        self.search_frame.setMaximumHeight(60)
        
        search_layout = QHBoxLayout(self.search_frame)
        search_layout.setContentsMargins(10, 5, 10, 5)
        
        # Find label
        search_label = QLabel(_("Find:"))
        search_label.setStyleSheet("font-weight: bold;")
        search_layout.addWidget(search_label)
        
        # Find input - make it wider for better usability
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_("Enter text to find..."))
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.search_next)
        self.search_input.setMinimumWidth(300)  # Increased from 200 to 300
        
        # Add keyboard shortcuts for search navigation
        from PyQt6.QtGui import QKeySequence
        self.search_input.installEventFilter(self)
        
        search_layout.addWidget(self.search_input)
        
        # Search buttons - make them consistent height and remove hardcoded font sizes
        self.search_prev_button = QPushButton("↑")
        self.search_prev_button.setToolTip(_("Previous match (Shift+Enter)"))
        self.search_prev_button.clicked.connect(self.search_previous)
        self.search_prev_button.setEnabled(False)
        self.search_prev_button.setMaximumWidth(40)
        self.search_prev_button.setMinimumHeight(30)  # Ensure consistent height
        search_layout.addWidget(self.search_prev_button)
        
        self.search_next_button = QPushButton("↓")
        self.search_next_button.setToolTip(_("Next match (Enter)"))
        self.search_next_button.clicked.connect(self.search_next)
        self.search_next_button.setEnabled(False)
        self.search_next_button.setMaximumWidth(40)
        self.search_next_button.setMinimumHeight(30)  # Ensure consistent height
        search_layout.addWidget(self.search_next_button)
        
        # Clear button - make it bigger to accommodate different language translations
        self.clear_search_button = QPushButton(_("Clear"))
        self.clear_search_button.clicked.connect(self.clear_search)
        self.clear_search_button.setMaximumWidth(80)  # Increased from 60 to 80
        self.clear_search_button.setMinimumHeight(30)  # Ensure consistent height
        search_layout.addWidget(self.clear_search_button)
        
        # Results label
        self.search_results_label = QLabel("")
        self.search_results_label.setStyleSheet("color: #666;")
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
        loop_layout.setSpacing(8)  # Add some spacing between elements for better visual separation
        
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
        self.speed_down_btn.setMaximumWidth(40)  # Match search button width
        self.speed_down_btn.setMinimumHeight(30)  # Match search button height
        self.speed_down_btn.clicked.connect(self.decrease_speed)
        loop_layout.addWidget(self.speed_down_btn)
        
        self.speed_up_btn = QPushButton("+")
        self.speed_up_btn.setMaximumWidth(40)  # Match speed down button width
        self.speed_up_btn.setMinimumHeight(30)  # Match search button height
        self.speed_up_btn.clicked.connect(self.increase_speed)
        loop_layout.addWidget(self.speed_up_btn)
        
        # Initialize speed control with current value from audio player
        self.initialize_speed_control()
        
        # Visual separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.VLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        separator2.setMaximumHeight(20)
        loop_layout.addWidget(separator2)
        
        # Scroll to current button
        self.scroll_to_current_button = QPushButton(_("Scroll to Current"))
        self.scroll_to_current_button.setIcon(ScrollToCurrentIcon(self))
        self.scroll_to_current_button.setToolTip(_("Scroll to the currently spoken text"))
        self.scroll_to_current_button.clicked.connect(self.on_scroll_to_current_button_clicked)
        self.scroll_to_current_button.setMinimumHeight(30)
        self.scroll_to_current_button.setStyleSheet("QPushButton { padding: 4px 8px; }")  # Better padding
        loop_layout.addWidget(self.scroll_to_current_button)
        
        loop_layout.addStretch()
        
        # Initially hide the loop controls frame
        self.loop_controls_frame.hide()

    def show_loop_controls(self):
        """Show the loop controls when audio is playing"""
        self.loop_controls_frame.show()
        
        # Save the visibility state to settings
        self.playback_controls_visible = True
        self.settings.settings.setValue("transcription_viewer/playback_controls_visible", self.playback_controls_visible)

    def hide_loop_controls(self):
        """Hide the loop controls when audio is not playing"""
        self.loop_controls_frame.hide()
        
        # Save the visibility state to settings
        self.playback_controls_visible = False
        self.settings.settings.setValue("transcription_viewer/playback_controls_visible", self.playback_controls_visible)

    def toggle_playback_controls_visibility(self):
        """Toggle the visibility of playback controls manually"""
        if self.loop_controls_frame.isVisible():
            self.hide_loop_controls()
        else:
            self.show_loop_controls()

    def on_audio_playback_state_changed(self, state):
        """Handle audio playback state changes to automatically show/hide playback controls"""
        from PyQt6.QtMultimedia import QMediaPlayer
        
        if state == QMediaPlayer.PlaybackState.PlayingState:
            # Show playback controls when audio starts playing
            if self.view_mode == ViewMode.TIMESTAMPS:
                self.show_loop_controls()
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            # Hide playback controls when audio stops
            self.hide_loop_controls()

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

    def update_search_ui(self):
        """Update the search UI elements"""
        if self.search_results:
            # Show "1 of X matches" format for consistency with navigation
            if len(self.search_results) >= 100:
                self.search_results_label.setText(f"1 of 100+ matches")
            else:
                self.search_results_label.setText(f"1 of {len(self.search_results)} matches")
            self.search_prev_button.setEnabled(True)
            self.search_next_button.setEnabled(True)
            self.highlight_current_match()
        else:
            self.search_results_label.setText(_("No matches found"))
            self.search_prev_button.setEnabled(False)
            self.search_next_button.setEnabled(False)

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
            if len(self.search_results) >= 100:
                self.search_results_label.setText(f"{self.current_search_index + 1} of 100+ matches")
            else:
                self.search_results_label.setText(f"{self.current_search_index + 1} of {len(self.search_results)} matches")

    def clear_search(self):
        """Clear the search and reset highlighting"""
        self.search_text = ""
        self.search_results = []
        self.current_search_index = 0
        self.search_input.clear()
        self.search_results_label.setText("")

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
        self.find_button.setChecked(False)  # Sync button state
        self.clear_search()
        self.search_input.clearFocus()
        
        # Save the visibility state to settings
        self.find_widget_visible = False
        self.settings.settings.setValue("transcription_viewer/find_widget_visible", False)

    def setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        from PyQt6.QtGui import QShortcut, QKeySequence
        
        # Search shortcut (Ctrl+F)
        search_shortcut = QShortcut(QKeySequence(self.shortcuts.get(Shortcut.SEARCH_TRANSCRIPT)), self)
        search_shortcut.activated.connect(self.focus_search_input)
        
        # Scroll to current text shortcut (Ctrl+G)
        scroll_to_current_shortcut = QShortcut(QKeySequence(self.shortcuts.get(Shortcut.SCROLL_TO_CURRENT_TEXT)), self)
        scroll_to_current_shortcut.activated.connect(self.on_scroll_to_current_button_clicked)
        
        # Playback controls visibility shortcut (Ctrl+P)
        playback_controls_shortcut = QShortcut(QKeySequence(self.shortcuts.get(Shortcut.TOGGLE_PLAYBACK_CONTROLS)), self)
        playback_controls_shortcut.activated.connect(self.toggle_playback_controls_visibility)

    def focus_search_input(self):
        """Toggle the search bar visibility and focus the input field"""
        if self.search_frame.isVisible():
            self.hide_search_bar()
        else:
            self.search_frame.show()
            self.find_button.setChecked(True)  # Sync button state
            self.search_input.setFocus()
            self.search_input.selectAll()
            
            # Save the visibility state to settings
            self.find_widget_visible = True
            self.settings.settings.setValue("transcription_viewer/find_widget_visible", True)

    def toggle_search_bar_visibility(self):
        """Toggle the search bar visibility"""
        if self.search_frame.isVisible():
            self.hide_search_bar()
        else:
            self.show_search_bar()
        
        # Save the visibility state to settings
        self.find_widget_visible = self.search_frame.isVisible()
        self.settings.settings.setValue("transcription_viewer/find_widget_visible", self.find_widget_visible)

    def show_search_bar(self):
        """Show the search bar and focus the input"""
        self.search_frame.show()
        self.find_button.setChecked(True)
        self.search_input.setFocus()
        self.search_input.selectAll()
        
        # Save the visibility state to settings
        self.find_widget_visible = True
        self.settings.settings.setValue("transcription_viewer/find_widget_visible", True)

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
            # Show playback controls in timestamps mode
            if self.playback_controls_visible:
                self.loop_controls_frame.show()
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
            # Hide playback controls in text mode
            self.loop_controls_frame.hide()
            # Hide current segment display in text mode
            self.current_segment_frame.hide()
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
            # Hide playback controls in translation mode
            self.loop_controls_frame.hide()
            # Hide current segment display in translation mode
            self.current_segment_frame.hide()
        
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
        
        # Show the current segment frame and update the text
        self.current_segment_frame.show()
        self.current_segment_text.setText(segment.value("text"))
        
        # Force the text label to recalculate its size
        self.current_segment_text.adjustSize()
        
        # Resize the frame to fit the text content
        self.resize_current_segment_frame()
        
        # Ensure the scroll area updates properly and shows scrollbars when needed
        self.current_segment_scroll_area.updateGeometry()
        self.current_segment_scroll_area.verticalScrollBar().setVisible(True)  # Ensure scrollbar is visible
        
        start_time = segment.value("start_time")
        end_time = segment.value("end_time")
        self.audio_player.set_position(start_time)
        
        if self.segment_looping_enabled:
            self.audio_player.set_range((start_time, end_time))
            
            # Reset looping flag to ensure new loops work
            self.audio_player.is_looping = False
        else:
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
            self.current_segment_text.setText(current_segment.value("text"))
            self.current_segment_frame.show()  # Show the frame when there's a current segment
            
            # Force the text label to recalculate its size
            self.current_segment_text.adjustSize()
            
            # Resize the frame to fit the text content
            self.resize_current_segment_frame()
            
            # Ensure the scroll area updates properly and shows scrollbars when needed
            self.current_segment_scroll_area.updateGeometry()
            self.current_segment_scroll_area.verticalScrollBar().setVisible(True)  # Ensure scrollbar is visible
            
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

    def resize_current_segment_frame(self):
        """
        Resize the current segment frame to fit its content, using the actual rendered size
        of the text label (including line wrapping). This ensures the frame is tall enough
        for the visible text, up to a reasonable maximum.
        """
        text = self.current_segment_text.text()
        if not text:
            self.current_segment_frame.setMaximumHeight(0)
            self.current_segment_frame.setMinimumHeight(0)
            return

        # Calculate the height needed for the text area
        line_height = self.current_segment_text.fontMetrics().lineSpacing()
        max_visible_lines = 3  # Fixed at 3 lines for consistency and clean UI
        
        # Calculate the height needed for the maximum visible lines (25% larger)
        text_height = line_height * max_visible_lines * 1.25
        
        # Add some vertical margins/padding
        margins = 8  # Increased from 2 to 8 for better spacing
        
        # Calculate total height needed (no header height anymore)
        total_height = text_height + margins
        
        # Convert to integer since Qt methods expect int values
        total_height = int(total_height)
        
        # Set maximum height to ensure consistent sizing, but allow minimum to be flexible
        self.current_segment_frame.setMaximumHeight(total_height)
        self.current_segment_frame.setMinimumHeight(total_height)
        
        # Convert text_height to integer since Qt methods expect int values
        text_height = int(text_height)
        
        # Allow the scroll area to be flexible in height for proper scrolling
        self.current_segment_scroll_area.setMinimumHeight(text_height)
        self.current_segment_scroll_area.setMaximumHeight(text_height)
        
        # Allow the text label to size naturally for proper scrolling
        self.current_segment_text.setMinimumHeight(text_height)

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
            self.auto_scroll_to_current_position()
        else:
            # If we have a selected segment, highlight it and keep it highlighted
            if self.currently_selected_segment is not None:
                segments = self.table_widget.segments()
                for i, segment in enumerate(segments):
                    if segment.value("id") == self.currently_selected_segment.value("id"):
                        self.table_widget.highlight_and_scroll_to_row(i)
                        break

    def on_scroll_to_current_button_clicked(self):
        """Handle scroll to current button click"""
        current_pos = self.audio_player.position_ms
        segments = self.table_widget.segments()

        # Find the current segment based on audio position
        current_segment_index = 0
        current_segment = segments[0]
        for i, segment in enumerate(segments):
            if segment.value("start_time") <= current_pos < segment.value("end_time"):
                current_segment_index = i
                current_segment = segment
                break

        # Workaround for scrolling to already selected segment
        if self.currently_selected_segment and self.currently_selected_segment.value("id") == current_segment.value('id'):
            self.highlight_table_match(0)

        if self.currently_selected_segment is None:
            self.highlight_table_match(0)

        if current_segment_index == 0 and segments[1]:
            self.highlight_table_match(1)

        self.highlight_table_match(current_segment_index)

    def auto_scroll_to_current_position(self):
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
                        break
                
        except Exception as e:
            pass  # Silently handle any errors

    def resizeEvent(self, event):
        """Save geometry when widget is resized"""
        self.save_geometry()
        super().resizeEvent(event)

    def closeEvent(self, event):
        """Save geometry when widget is closed"""
        self.save_geometry()
        self.hide()

        if self.transcription_resizer_dialog:
            self.transcription_resizer_dialog.close()

        self.translator.stop()
        self.translation_thread.quit()
        self.translation_thread.wait()

        super().closeEvent(event)

    def save_geometry(self):
        """Save the widget geometry to settings"""
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_VIEWER)
        self.settings.settings.setValue("geometry", self.saveGeometry())
        self.settings.end_group()

    def load_geometry(self):
        """Load the widget geometry from settings"""
        self.settings.begin_group(Settings.Key.TRANSCRIPTION_VIEWER)
        geometry = self.settings.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            # Default size if no saved geometry
            self.resize(1000, 800)
        self.settings.end_group()
