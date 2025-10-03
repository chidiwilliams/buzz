# Transcription Viewer Interface

The Buzz transcription viewer provides a powerful interface for reviewing, editing, and navigating through your transcriptions. This guide covers all the features available in the transcription viewer.

## Overview

The transcription viewer is organized into several key sections:

- **Top Toolbar**: Contains view mode, export, translate, resize, and search
- **Search Bar**: Find and navigate through transcript text
- **Transcription Segments**: Table view of all transcription segments with timestamps
- **Playback Controls**: Audio playback settings and speed controls (since version 1.3.0)
- **Audio Player**: Standard media player with progress bar
- **Current Segment Display**: Shows the currently selected or playing segment

## Top Toolbar

### View Mode Button
- **Function**: Switch between different viewing modes
- **Options**:
  - **Timestamps**: Shows segments in a table format with start/end times
  - **Text**: Shows combined text without timestamps
  - **Translation**: Shows translated text (if available)

### Export Button
- **Function**: Export transcription in various formats
- **Formats**: SRT, VTT, TXT, JSON, and more
- **Usage**: Click to open export menu and select desired format

### Translate Button
- **Function**: Translate transcription to different languages
- **Usage**: Click to open translation settings and start translation

### Resize Button
- **Function**: Adjust transcription segment boundaries
- **Usage**: Click to open resize dialog for fine-tuning timestamps
- **More information**: See [Edit and Resize](https://chidiwilliams.github.io/buzz/docs/usage/edit_and_resize) section

### Playback Controls Button
(since version 1.3.0)
- **Function**: Show/hide playback control panel
- **Shortcut**: `Ctrl+Alt+P` (Windows/Linux) or `Cmd+Alt+P` (macOS)
- **Behavior**: Toggle button that shows/hides the playback controls below

### Find Button
(since version 1.3.0)
- **Function**: Show/hide search functionality
- **Shortcut**: `Ctrl+F` (Windows/Linux) or `Cmd+F` (macOS)
- **Behavior**: Toggle button that shows/hides the search bar

### Scroll to Current Button
(since version 1.3.0)
- **Function**: Automatically scroll to the currently playing text
- **Shortcut**: `Ctrl+G` (Windows/Linux) or `Cmd+G` (macOS)
- **Usage**: Click to jump to the current audio position in the transcript

## Search Functionality
(since version 1.3.0)

### Search Bar
The search bar appears below the toolbar when activated and provides:

- **Search Input**: Type text to find in the transcription (wider input field for better usability)
- **Navigation**: Up/down arrows to move between matches
- **Status**: Shows current match position and total matches (e.g., "3 of 15 matches")
- **Clear**: Remove search text and results (larger button for better accessibility)
- **Results**: Displays found text with context
- **Consistent Button Sizing**: All navigation buttons have uniform height for better visual consistency

### Search Shortcuts
- **`Ctrl+F` / `Cmd+F`**: Toggle search bar on/off
- **`Enter`**: Find next match
- **`Shift+Enter`**: Find previous match
- **`Escape`**: Close search bar

### Search Features
- **Real-time Search**: Results update as you type
- **Case-insensitive**: Finds matches regardless of capitalization
- **Word Boundaries**: Respects word boundaries for accurate matching
- **Cross-view Search**: Works in all view modes (Timestamps, Text, Translation)

## Playback Controls
(since version 1.3.0)

### Loop Segment
- **Function**: Automatically loop playback of selected segments
- **Usage**: Check the "Loop Segment" checkbox
- **Behavior**: When enabled, clicking on a transcript segment will set a loop range
- **Visual Feedback**: Loop range is highlighted in the audio player

### Follow Audio
- **Function**: Automatically scroll to current audio position
- **Usage**: Check the "Follow Audio" checkbox
- **Behavior**: Transcript automatically follows the audio playback
- **Benefits**: Easy to follow along with long audio files

### Speed Controls
- **Function**: Adjust audio playback speed
- **Range**: 0.5x to 2.0x speed
- **Controls**:
  - **Speed Dropdown**: Select from preset speeds or enter custom value
  - **Decrease Button (-)**: Reduce speed by 0.05x increments
  - **Increase Button (+)**: Increase speed by 0.05x increments
- **Persistence**: Speed setting is saved between sessions
- **Button Sizing**: Speed control buttons match the size of search navigation buttons for visual consistency

## Keyboard Shortcuts

### Audio Playback
- **`Ctrl+P` / `Cmd+P`**: Play/Pause audio
- **`Ctrl+Shift+P` / `Cmd+Shift+P`**: Replay current segment from start

### Timestamp Adjustment
- **`Ctrl+←` / `Cmd+←`**: Decrease segment start time by 0.5s
- **`Ctrl+→` / `Cmd+→`**: Increase segment start time by 0.5s
- **`Ctrl+Shift+←` / `Cmd+Shift+←`**: Decrease segment end time by 0.5s
- **`Ctrl+Shift+→` / `Cmd+Shift+→`**: Increase segment end time by 0.5s

### Navigation
- **`Ctrl+F` / `Cmd+F`**: Toggle search bar
- **`Ctrl+Alt+P` / `Cmd+Alt+P`**: Toggle playback controls
- **`Ctrl+G` / `Cmd+G`**: Scroll to current position
- **`Ctrl+O` / `Cmd+O`**: Open file import dialog

### Search
- **`Enter`**: Find next match
- **`Shift+Enter`**: Find previous match
- **`Escape`**: Close search bar
