from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from audio_playground.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AI Audio Playground")
    app.setOrganizationName("AI Audio Playground")
    app.setStyle("Fusion")
    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    exit_code = app.exec()
    window.cleanup_session_files()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
