from pathlib import Path

import pytest

from mediashrink.common import (
    atomic_output,
    collect_inputs,
    human_size,
    is_dir_target,
    output_path,
    resolve_output,
    temp_path,
)


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


def test_missing_output_dir_without_extension_is_created(tmp_path: Path):
    # `-o out/` reaches us as Path("out"): pathlib drops the trailing slash.
    src = tmp_path / "a.png"
    src.touch()
    out = tmp_path / "out"
    assert resolve_output(src, Path(f"{out}/"), ".jpg") == out / "a.jpg"
    assert out.is_dir()


def test_is_dir_target(tmp_path: Path):
    assert is_dir_target(tmp_path)  # existing dir
    assert is_dir_target(tmp_path / "new")  # missing, no extension
    assert not is_dir_target(tmp_path / "new.mp4")  # missing file path
    (tmp_path / "plain").touch()
    assert not is_dir_target(tmp_path / "plain")  # existing file


def _touch(*paths: Path) -> None:
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()


def test_collect_inputs(tmp_path: Path):
    d = tmp_path / "in"
    _touch(d / "b.jpg", d / "a.PNG", d / "notes.txt", d / "a.min.jpg", d / ".part-x.jpg", d / ".hidden" / "h.jpg")
    _touch(d / "sub" / "c.jpg", d / "sub" / "deeper" / "e.jpg", d / "out" / "a.jpg")
    exts = {".jpg", ".png"}
    names = [(p.name, str(s)) for p, s in collect_inputs([d], exts)]
    assert names == [("a.PNG", "."), ("b.jpg", ".")]  # sorted; no other types, earlier outputs or hidden files
    rec = [(p.name, s.as_posix()) for p, s in collect_inputs([d], exts, recursive=True, exclude=d / "out")]
    assert rec == [("a.PNG", "."), ("b.jpg", "."), ("c.jpg", "sub"), ("e.jpg", "sub/deeper")]
    # a file given directly is always taken, and a file reached twice only once
    assert [p.name for p, _ in collect_inputs([d / "notes.txt", d, d / "b.jpg"], exts)] == [
        "notes.txt",
        "a.PNG",
        "b.jpg",
    ]


def test_output_path_mirrors_subdir(tmp_path: Path):
    out = tmp_path / "out"
    assert output_path(Path("in/sub/a.png"), out, ".jpg", Path("sub")) == out / "sub" / "a.jpg"
    assert output_path(Path("in/sub/a.png"), None, ".jpg", Path("sub")) == Path("in/sub/a.min.jpg")
