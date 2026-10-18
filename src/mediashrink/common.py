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


def output_path(src: Path, output: Path | None, suffix: str) -> Path:
    """Pick the output path (no checks).

    - `output` is a directory -> <output>/<stem><suffix>
    - `output` is a file path -> used as-is
    - no `output` -> <src dir>/<stem>.min<suffix>
    """
    if output is None:
        return src.with_name(f"{src.stem}.min{suffix}")
    if output.is_dir():
        return output / f"{src.stem}{suffix}"
    return output


def resolve_output(src: Path, output: Path | None, suffix: str, overwrite: bool = False) -> Path:
    """`output_path()`, refusing to overwrite the input, or an existing file unless `overwrite`."""
    dst = output_path(src, output, suffix)
    if dst.resolve() == src.resolve():
        raise ValueError(f"Output would overwrite the input file: {src}")
    if dst.exists() and not overwrite:
        raise FileExistsError(f"Output already exists (use --overwrite): {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    return dst


def temp_path(dst: Path) -> Path:
    """Hidden sibling of `dst` that keeps its extension (encoders pick the format from it)."""
    return dst.with_name(f".{dst.stem}.part{dst.suffix}")


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
