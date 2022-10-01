from gui import Application


def test_application():
    app = Application()
    assert app.window.windowTitle() == 'Buzz'
