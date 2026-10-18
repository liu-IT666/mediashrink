"""Shared helpers: output path resolution and size reporting."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Result:
    src: Path
    dst: Path

    @property
    def src_size(self) -> int:
        return self.src.stat().st_size

    @property
    def dst_size(self) -> int:
        return self.dst.stat().st_size

    @property
    def ratio(self) -> float:
        return self.dst_size / self.src_size if self.src_size else 0.0


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def is_dir_target(output: Path) -> bool:
    """`--output` names a directory: an existing one, or a new path without an extension.

    (`-o out/` arrives here as `out`: pathlib drops the trailing slash. An output *file*
    without an extension is useless anyway, since encoders pick the format from it.)
    """
    return output.is_dir() or (not output.exists() and not output.suffix)


def output_path(src: Path, output: Path | None, suffix: str, subdir: Path = Path()) -> Path:
    """Pick the output path (no checks).

    - `output` is a directory (see `is_dir_target`) -> <output>/<subdir>/<stem><suffix>
      (`subdir` is where `src` sits inside a directory input, see `collect_inputs`)
    - `output` is a file path -> used as-is
    - no `output` -> <src dir>/<stem>.min<suffix>
    """
    if output is None:
        return src.with_name(f"{src.stem}.min{suffix}")
    if is_dir_target(output):
        return output / subdir / f"{src.stem}{suffix}"
    return output


def resolve_output(src: Path, output: Path | None, suffix: str, overwrite: bool = False, subdir: Path = Path()) -> Path:
    """`output_path()`, refusing to overwrite the input, or an existing file unless `overwrite`."""
    dst = output_path(src, output, suffix, subdir)
    if dst.resolve() == src.resolve():
        raise ValueError(f"Output would overwrite the input file: {src}")
    if dst.exists() and not overwrite:
        raise FileExistsError(f"Output already exists (use --overwrite): {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    return dst


def collect_inputs(
    inputs: list[Path], exts: set[str], recursive: bool = False, exclude: Path | None = None
) -> list[tuple[Path, Path]]:
    """Expand directory inputs into `(file, subdir)` pairs; files are passed through as `(file, .)`.

    In a directory, only files whose extension is in `exts` are taken, in name order,
    skipping hidden files and directories, earlier outputs (`*.min.*`) and anything under
    `exclude` (the output directory). Subdirectories are walked only when `recursive`;
    `subdir` is then the file's directory relative to the input directory, so a directory
    `-o` mirrors the input tree. A file reached twice is kept once.
    """
    skip = exclude.resolve() if exclude is not None else None
    seen: set[Path] = set()
    found: list[tuple[Path, Path]] = []

    def add(path: Path, subdir: Path) -> None:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            found.append((path, subdir))

    for item in inputs:
        if not item.is_dir():
            add(item, Path())
            continue
        walk = sorted(item.rglob("*") if recursive else item.iterdir())
        for path in walk:
            rel = path.relative_to(item)
            if any(part.startswith(".") for part in rel.parts) or not path.is_file():
                continue
            if skip is not None and path.resolve().is_relative_to(skip):
                continue
            if path.suffix.lower() in exts and not path.stem.endswith(".min"):
                add(path, rel.parent)
    return found


def temp_path(dst: Path) -> Path:
    """Hidden sibling of `dst` with the same extension (encoders pick the format from it)."""
    return dst.with_name(f".part-{dst.name}")


@contextmanager
def atomic_output(dst: Path) -> Iterator[Path]:
    """Yield a temp path to write to; it replaces `dst` only if the block succeeds.

    On any error (including Ctrl+C) the temp file is removed, so a failed run never
    leaves a truncated `dst` behind.
    """
    tmp = temp_path(dst)
    try:
        yield tmp
        if tmp.exists():
            os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
