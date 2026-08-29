from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import QApplication

from audio_playground.main_window import MainWindow
from audio_playground.config import PRODUCT_NAME, PROJECT_ROOT, WINDOW_BACKGROUND_RGB
from audio_playground.hot_reload import HotReloadWatcher
from audio_playground.macos import set_bundle_name, style_titlebar


def main() -> int:
    set_bundle_name(PRODUCT_NAME)
    app = QApplication(sys.argv)
    # Keep the legacy settings identity so the rebrand does not hide saved presets.
    app.setApplicationName("AI Audio Playground")
    app.setApplicationDisplayName(PRODUCT_NAME)
    app.setOrganizationName("AI Audio Playground")
    app.setStyle("Fusion")
    window = MainWindow()
    app.setWindowIcon(window.windowIcon())
    app.aboutToQuit.connect(window.shutdown)
    hot_reload = None
    if os.environ.get("AUDIO_PLAYGROUND_HOT_RELOAD") == "1":
        hot_reload = HotReloadWatcher(app, PROJECT_ROOT)
        window.status_label.setText("Development hot reload enabled")
    window.show()
    style_titlebar(int(window.winId()), WINDOW_BACKGROUND_RGB)
    exit_code = app.exec()
    _ = hot_reload
    window.cleanup_session_files()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
