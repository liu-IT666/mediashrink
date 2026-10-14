from pathlib import Path

import pytest

from mediashrink.common import human_size, resolve_output


def test_default_output_name(tmp_path: Path):
    src = tmp_path / "a.png"
    src.touch()
    assert resolve_output(src, None, ".webp") == tmp_path / "a.min.webp"


def test_output_dir(tmp_path: Path):
    src = tmp_path / "a.png"
    src.touch()
    out = tmp_path / "out"
    out.mkdir()
    assert resolve_output(src, out, ".jpg") == out / "a.jpg"


def test_refuses_to_overwrite_input(tmp_path: Path):
    src = tmp_path / "a.png"
    src.touch()
    with pytest.raises(ValueError):
        resolve_output(src, src, ".png", overwrite=True)


def test_refuses_existing_without_flag(tmp_path: Path):
    src = tmp_path / "a.png"
    src.touch()
    (tmp_path / "a.min.png").touch()
    with pytest.raises(FileExistsError):
        resolve_output(src, None, ".png")
    assert resolve_output(src, None, ".png", overwrite=True) == tmp_path / "a.min.png"


def test_human_size():
    assert human_size(512) == "512.0 B"
    assert human_size(1536) == "1.5 KB"
