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
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

