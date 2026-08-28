from audio_playground.hot_reload import source_files


def test_hot_reload_watches_application_python_files(tmp_path) -> None:
    package = tmp_path / "audio_playground"
    package.mkdir()
    source = package / "main_window.py"
    source.write_text("# source\n")
    ignored = package / "notes.txt"
    ignored.write_text("not source\n")
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\n")

    watched = source_files(tmp_path)

    assert str(source) in watched
    assert str(pyproject) in watched
    assert str(ignored) not in watched
