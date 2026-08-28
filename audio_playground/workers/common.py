from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any


_output_lock = threading.Lock()


def emit(event: str, **data: Any) -> None:
    with _output_lock:
        print(json.dumps({"event": event, **data}), flush=True)


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


@contextmanager
def monitor_phase(label: str, interval: float = 10):
    """Emit elapsed-time heartbeats around a long blocking operation."""
    stopped = threading.Event()
    started = time.monotonic()

    def monitor() -> None:
        while not stopped.wait(interval):
            emit(
                "status",
                message=f"{label} · elapsed {_format_duration(time.monotonic() - started)}",
            )

    emit("status", message=f"{label}…")
    emit("progress", value=-1, label=label)
    thread = threading.Thread(target=monitor, name="phase-monitor", daemon=True)
    thread.start()
    try:
        yield
    except Exception:
        emit(
            "status",
            message=f"{label} failed after {_format_duration(time.monotonic() - started)}.",
        )
        raise
    else:
        emit(
            "status",
            message=f"{label} completed in {_format_duration(time.monotonic() - started)}.",
        )
    finally:
        stopped.set()
        thread.join(timeout=1)


def _repo_cache_state(repo_id: str) -> tuple[int, tuple[tuple[str, int], ...]]:
    cache_root = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    blob_dir = cache_root / "hub" / f"models--{repo_id.replace('/', '--')}" / "blobs"
    if not blob_dir.is_dir():
        return 0, ()

    largest_by_blob: dict[str, int] = {}
    signature: list[tuple[str, int]] = []
    for path in blob_dir.iterdir():
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        signature.append((path.name, size))
        blob_id = path.name.split(".", 1)[0]
        largest_by_blob[blob_id] = max(largest_by_blob.get(blob_id, 0), size)
    return sum(largest_by_blob.values()), tuple(sorted(signature))


def _model_cache_complete(cached_bytes: int, expected_bytes: int) -> bool:
    # Repository-size constants are approximate and may vary slightly by Hub revision.
    return expected_bytes > 0 and cached_bytes >= expected_bytes * 0.99


@contextmanager
def monitor_model_download(repo_id: str, expected_bytes: int):
    """Distinguish downloading files from loading cached weights into memory."""
    stopped = threading.Event()

    def monitor() -> None:
        started = time.monotonic()
        cached_bytes, last_signature = _repo_cache_state(repo_id)
        last_activity = time.monotonic()
        while not stopped.is_set():
            cached_bytes, signature = _repo_cache_state(repo_id)
            if signature != last_signature:
                last_signature = signature
                last_activity = time.monotonic()
            percent = min(cached_bytes / expected_bytes * 100, 100.0)
            elapsed = _format_duration(time.monotonic() - started)
            if _model_cache_complete(cached_bytes, expected_bytes):
                emit(
                    "status",
                    message=(
                        f"Model cache complete ({_format_bytes(cached_bytes)}); loading and "
                        f"validating weights in memory · elapsed {elapsed}"
                    ),
                )
                emit("progress", value=-1, label="Loading model into memory")
                stopped.wait(10)
                continue

            idle_seconds = int(time.monotonic() - last_activity)
            if idle_seconds < 30:
                activity = "transfer active"
            elif idle_seconds < 120:
                activity = f"waiting for data ({idle_seconds}s)"
            else:
                activity = f"possible stall: no new bytes for {idle_seconds}s"
            emit(
                "status",
                message=(
                    f"Model cache: {_format_bytes(cached_bytes)} / "
                    f"{_format_bytes(expected_bytes)} ({percent:.1f}%) · {activity} · "
                    f"elapsed {elapsed}"
                ),
            )
            emit("progress", value=round(percent), label="Downloading model")
            stopped.wait(10)

    thread = threading.Thread(target=monitor, name="model-download-monitor", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=1)


def run_worker(generate: Callable[[dict[str, Any]], str]) -> None:
    emit("ready")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("command") == "quit":
                return
            if request.get("command") != "generate":
                raise ValueError("Unsupported worker command")
            path = generate(request)
            emit("result", path=path)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            emit("error", message=f"{type(exc).__name__}: {exc}")
