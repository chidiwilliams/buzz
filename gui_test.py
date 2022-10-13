from gui import Application, LanguagesComboBox


class TestApplication:
    app = Application()

    def test_should_show_window_title(self):
        assert len(self.app.windows) == 1
        assert self.app.windows[0].windowTitle() == 'Buzz'

    def test_should_open_a_new_live_recording_window(self):
        main_window = self.app.windows[0]
        new_live_recording_action = main_window.file_menu.actions()[0]

        assert new_live_recording_action.text() == '&New Live Recording'

        new_live_recording_action.trigger()

        assert len(self.app.windows) == 2

        new_window = self.app.windows[1]
        assert new_window.windowTitle() == 'Buzz'


class TestLanguagesComboBox:
    languagesComboxBox = LanguagesComboBox('en')

    def test_should_show_sorted_whisper_languages(self):
        assert self.languagesComboxBox.itemText(0) == 'Detect Language'
        assert self.languagesComboxBox.itemText(10) == 'Belarusian'
        assert self.languagesComboxBox.itemText(20) == 'Dutch'
        assert self.languagesComboxBox.itemText(30) == 'Gujarati'
        assert self.languagesComboxBox.itemText(40) == 'Japanese'
        assert self.languagesComboxBox.itemText(50) == 'Lithuanian'

    def test_should_select_default_language(self):
        assert self.languagesComboxBox.currentText() == 'English'
