from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import QApplication

from audio_playground.main_window import MainWindow
from audio_playground.config import PROJECT_ROOT
from audio_playground.hot_reload import HotReloadWatcher


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AI Audio Playground")
    app.setOrganizationName("AI Audio Playground")
    app.setStyle("Fusion")
    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown)
    hot_reload = None
    if os.environ.get("AUDIO_PLAYGROUND_HOT_RELOAD") == "1":
        hot_reload = HotReloadWatcher(app, PROJECT_ROOT)
        window.status_label.setText("Development hot reload enabled")
    window.showMaximized()
    exit_code = app.exec()
    _ = hot_reload
    window.cleanup_session_files()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
