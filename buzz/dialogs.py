from PyQt6.QtWidgets import QWidget, QMessageBox


def show_model_download_error_dialog(parent: QWidget, error: str):
    message = (
        parent.tr("An error occurred while loading the Whisper model")
        + f": {error}{'' if error.endswith('.') else '.'}"
        + parent.tr("Please retry or check the application logs for more information.")
    )

    QMessageBox.critical(parent, "", message)
