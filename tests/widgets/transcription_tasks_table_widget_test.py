from buzz.widgets.transcription_tasks_table_widget import TranscriptionTasksTableWidget


class TestTranscriptionTasksTableWidget:
    def test_can_create(self, qtbot, reset_settings):
        widget = TranscriptionTasksTableWidget()
        qtbot.add_widget(widget)
