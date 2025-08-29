# Transcription Viewer Interface

The Buzz transcription viewer provides a powerful interface for reviewing, editing, and navigating through your transcriptions. This guide covers all the features available in the transcription viewer.

## Overview

The transcription viewer is organized into several key sections:

- **Top Toolbar**: Contains view mode, export, translate, resize, and playback control buttons
- **Search Bar**: Find and navigate through transcript text
- **Transcription Segments**: Table view of all transcription segments with timestamps
- **Playback Controls**: Audio playback settings and speed controls
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
- **Requirements**: OpenAI API key configured
- **Usage**: Click to open translation settings and start translation

### Resize Button
- **Function**: Adjust transcription segment boundaries
- **Usage**: Click to open resize dialog for fine-tuning timestamps

### Playback Controls Button
- **Function**: Show/hide playback control panel
- **Shortcut**: `Ctrl+L` (Windows/Linux) or `Cmd+L` (macOS)
- **Behavior**: Toggle button that shows/hides the playback controls below

### Find Button
- **Function**: Show/hide search functionality
- **Shortcut**: `Ctrl+F` (Windows/Linux) or `Cmd+F` (macOS)
- **Behavior**: Toggle button that shows/hides the search bar

### Scroll to Current Button
- **Function**: Automatically scroll to the currently playing text
- **Shortcut**: `Ctrl+G` (Windows/Linux) or `Cmd+G` (macOS)
- **Usage**: Click to jump to the current audio position in the transcript

## Search Functionality

### Search Bar
The search bar appears below the toolbar when activated and provides:

- **Search Input**: Type text to find in the transcription
- **Navigation**: Up/down arrows to move between matches
- **Status**: Shows current match position and total matches
- **Clear**: Remove search text and results
- **Results**: Displays found text with context

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

## Audio Player

### Standard Controls
- **Play/Pause**: Standard media player controls
- **Progress Bar**: Visual representation of current position
- **Time Display**: Shows current time and total duration
- **Seek**: Click on progress bar to jump to specific position

### Enhanced Features
- **Segment Navigation**: Click on transcript segments to jump to that time
- **Loop Support**: Visual indication of loop ranges
- **Speed Control**: Integrated with playback controls above

## Current Segment Display

### Enhanced Text Display
- **Header**: Clear "Current Segment:" label
- **Text Area**: Dedicated display for current segment text
- **Scroll Support**: Handles long text segments gracefully
- **Auto-hide**: Only visible when there's a current segment to show

### Smart Visibility
- **Segment Selection**: Appears when clicking on transcript segments
- **Audio Playback**: Shows current segment during playback
- **Clean Interface**: No empty frames when not needed

## Keyboard Shortcuts

### Navigation
- **`Ctrl+F` / `Cmd+F`**: Toggle search bar
- **`Ctrl+P` / `Cmd+P`**: Toggle playback controls
- **`Ctrl+G` / `Cmd+G`**: Scroll to current position
- **`Ctrl+O` / `Cmd+O`**: Open file import dialog

### Search
- **`Enter`**: Find next match
- **`Shift+Enter`**: Find previous match
- **`Escape`**: Close search bar

### View Modes
- **`Ctrl+1`**: Switch to Timestamps view
- **`Ctrl+2`**: Switch to Text view
- **`Ctrl+3`**: Switch to Translation view

## User Experience Features

### Conditional Visibility
- **Smart Controls**: Playback controls only appear when audio is playing
- **Context-Aware**: Search bar only shows when needed
- **Clean Interface**: No clutter when features aren't relevant

### State Persistence
- **UI Preferences**: Remembers your preferred interface layout
- **Control Visibility**: Saves which panels were open/closed
- **Speed Settings**: Remembers playback speed preferences
- **Search State**: Maintains search text between sessions

### Professional Interface
- **Modern Design**: Clean, professional appearance
- **Consistent Layout**: Logical organization of controls
- **Responsive Design**: Adapts to different window sizes
- **Accessibility**: Keyboard shortcuts and clear labeling

## Tips and Best Practices

### Efficient Navigation
1. **Use keyboard shortcuts** for common actions
2. **Enable Follow Audio** for long transcriptions
3. **Use Loop Segment** for reviewing specific sections
4. **Adjust playback speed** for faster review

### Search Strategies
1. **Start with short search terms** for better results
2. **Use the navigation arrows** to move between matches
3. **Clear search** when done to return to normal view
4. **Combine with view modes** for different search contexts

### Playback Optimization
1. **Set appropriate speed** for your review needs
2. **Use loop controls** for repetitive review
3. **Enable follow audio** for hands-free navigation
4. **Save your preferences** for consistent experience

## Troubleshooting

### Common Issues

**Search not working?**
- Ensure search bar is visible (click Find button or press Ctrl+F)
- Check that you're in the correct view mode
- Verify text exists in the transcription

**Playback controls not visible?**
- Check if audio is playing (controls only show during playback)
- Use Ctrl+P to manually toggle controls
- Verify audio file is properly loaded

**Speed controls not responding?**
- Ensure playback controls are visible
- Check that audio player is active
- Try refreshing the interface

**Interface not remembering preferences?**
- Check that settings are being saved
- Verify application has write permissions
- Try restarting the application

### Getting Help
- Check the [FAQ](../faq.md) for common questions
- Review [preferences](../preferences.md) for configuration options
- Report issues on the [GitHub repository](https://github.com/chidiwilliams/buzz)

---

The transcription viewer provides a comprehensive interface for working with your transcriptions. Take advantage of the keyboard shortcuts and conditional visibility features to create an efficient workflow that matches your needs.
