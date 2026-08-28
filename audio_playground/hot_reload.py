from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication


HOT_RELOAD_EXIT_CODE = 75


def source_files(project_root: Path) -> list[str]:
    paths = [project_root / "pyproject.toml"]
    paths.extend((project_root / "audio_playground").rglob("*.py"))
    return [str(path) for path in paths if path.is_file()]


def _snapshot(project_root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for filename in source_files(project_root):
        try:
            stat = Path(filename).stat()
        except OSError:
            continue
        snapshot[filename] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


class HotReloadWatcher(QObject):
    """Exit with a distinct code when application source changes."""

    def __init__(self, app: QApplication, project_root: Path) -> None:
        super().__init__(app)
        self.app = app
        self.project_root = project_root
        self._reloading = False
        self._previous_snapshot = _snapshot(project_root)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def _poll(self) -> None:
        current_snapshot = _snapshot(self.project_root)
        if current_snapshot == self._previous_snapshot:
            return
        self._previous_snapshot = current_snapshot
        if self._reloading:
            return
        self._reloading = True
        self.timer.stop()
        QTimer.singleShot(100, lambda: self.app.exit(HOT_RELOAD_EXIT_CODE))
