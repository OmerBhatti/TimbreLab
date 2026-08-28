from audio_playground.workers.common import (
    _format_bytes,
    _format_duration,
    _model_cache_complete,
    _repo_cache_state,
)


def test_repo_cache_state_counts_largest_partial_per_blob(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    blobs = tmp_path / "hub" / "models--example--model" / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "first.old.incomplete").write_bytes(b"a" * 10)
    (blobs / "first.new.incomplete").write_bytes(b"a" * 20)
    (blobs / "second").write_bytes(b"b" * 5)

    cached_bytes, signature = _repo_cache_state("example/model")

    assert cached_bytes == 25
    assert len(signature) == 3


def test_format_bytes_uses_readable_units() -> None:
    assert _format_bytes(1024 * 1024 * 3) == "3.0 MB"


def test_format_duration_uses_clock_format() -> None:
    assert _format_duration(65) == "01:05"
    assert _format_duration(3661) == "1:01:01"


def test_model_cache_allows_small_repository_size_variance() -> None:
    assert _model_cache_complete(99, 100)
    assert not _model_cache_complete(98, 100)
