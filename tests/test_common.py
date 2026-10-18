from pathlib import Path

import pytest

from mediashrink.common import atomic_output, human_size, resolve_output, temp_path


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


def test_atomic_output_replaces_on_success(tmp_path: Path):
    dst = tmp_path / "a.min.jpg"
    with atomic_output(dst) as tmp:
        assert tmp.suffix == ".jpg" and tmp != dst
        tmp.write_text("new")
    assert dst.read_text() == "new"
    assert list(tmp_path.iterdir()) == [dst]


def test_atomic_output_cleans_up_on_error(tmp_path: Path):
    dst = tmp_path / "a.min.jpg"
    dst.write_text("old")
    with pytest.raises(RuntimeError), atomic_output(dst) as tmp:
        tmp.write_text("partial")
        raise RuntimeError("encoder failed")
    assert dst.read_text() == "old"  # previous output untouched
    assert not temp_path(dst).exists()
