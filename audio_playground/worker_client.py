from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

from audio_playground.config import PROJECT_ROOT


class WorkerClient(QObject):
    status = pyqtSignal(str)
    log = pyqtSignal(str)
    result = pyqtSignal(str)
    error = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)
    progress = pyqtSignal(int, str)

    def __init__(self, python_path: Path, module: str, parent: QObject | None = None):
        super().__init__(parent)
        self.python_path = python_path
        self.module = module
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(PROJECT_ROOT))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("HF_HUB_DISABLE_XET", "1")
        environment.insert("HF_HUB_DOWNLOAD_TIMEOUT", "120")
        environment.insert("HF_HUB_ETAG_TIMEOUT", "30")
        self.process.setProcessEnvironment(environment)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._finished)
        self._stdout_buffer = ""
        self._busy = False
        self._pending: dict[str, Any] | None = None
        self._cancel_requested = False

    @property
    def busy(self) -> bool:
        return self._busy

    def generate(self, payload: dict[str, Any]) -> None:
        if self._busy:
            self.error.emit("This engine is already generating audio.")
            return
        self._set_busy(True)
        if self.process.state() == QProcess.ProcessState.NotRunning:
            if not self.python_path.exists():
                self._set_busy(False)
                self.error.emit(
                    f"Worker environment not found: {self.python_path}\n"
                    "Run ./scripts/setup.sh first."
                )
                return
            self._pending = payload
            self._report("Starting engine worker…")
            self.process.start(str(self.python_path), ["-u", "-m", self.module])
            if not self.process.waitForStarted(3000):
                self._set_busy(False)
                self.error.emit(f"Could not start {self.module}.")
            return
        self._send(payload)

    def cancel(self) -> None:
        """Cancel model loading or generation by stopping the worker process."""
        if not self._busy:
            return
        self._cancel_requested = True
        self._pending = None
        self._report("Stopping engine…")
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self._finish_cancel()
            return
        self.process.terminate()
        QTimer.singleShot(2000, self._kill_if_running)

    def stop(self) -> None:
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self._pending = None
        if self._busy:
            self._cancel_requested = True
            self.process.terminate()
        else:
            self.process.write(b'{"command":"quit"}\n')
        self.process.waitForFinished(1500)
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(500)

    def _send(self, payload: dict[str, Any]) -> None:
        message = {"command": "generate", **payload}
        self.process.write((json.dumps(message) + "\n").encode())
        self._report("Generating… first use may download model weights.")

    def _read_stdout(self) -> None:
        self._stdout_buffer += bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self.log.emit(line.strip())
                continue
            event = message.get("event")
            if event == "ready":
                self._report("Engine ready.")
                if self._pending is not None:
                    payload, self._pending = self._pending, None
                    self._send(payload)
            elif event == "status":
                self._report(str(message.get("message", "Working…")))
            elif event == "progress":
                self.progress.emit(
                    int(message.get("value", -1)),
                    str(message.get("label", "Working")),
                )
            elif event == "result":
                self._set_busy(False)
                self.log.emit("Audio generated and ready for preview.")
                self.result.emit(str(message["path"]))
            elif event == "error":
                self._set_busy(False)
                error = str(message.get("message", "Unknown worker error"))
                self.log.emit(f"Error: {error}")
                self.error.emit(error)

    def _read_stderr(self) -> None:
        text = bytes(self.process.readAllStandardError()).decode(errors="replace").strip()
        if text:
            lines = [line.strip() for line in text.replace("\r", "\n").splitlines() if line.strip()]
            for line in lines:
                self.log.emit(line)
            self.status.emit(lines[-1][:240])

    def _process_error(self, _error: QProcess.ProcessError) -> None:
        if self._cancel_requested:
            return
        self._set_busy(False)
        self.error.emit(self.process.errorString())

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        was_busy = self._busy
        was_cancelled = self._cancel_requested
        self._cancel_requested = False
        self._pending = None
        self._stdout_buffer = ""
        self._set_busy(False)
        if was_cancelled:
            self._report("Stopped. You can generate again.")
        elif was_busy and exit_code:
            details = bytes(self.process.readAllStandardError()).decode(errors="replace").strip()
            self.error.emit(details[-1500:] or f"Worker exited with code {exit_code}.")

    def _kill_if_running(self) -> None:
        if self._cancel_requested and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _finish_cancel(self) -> None:
        self._cancel_requested = False
        self._set_busy(False)
        self._report("Stopped. You can generate again.")

    def _report(self, message: str) -> None:
        self.status.emit(message)
        self.log.emit(message)

    def _set_busy(self, busy: bool) -> None:
        if self._busy != busy:
            self._busy = busy
            self.busy_changed.emit(busy)
