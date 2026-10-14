"""Shared helpers: output path resolution and size reporting."""

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


def resolve_output(src: Path, output: Path | None, suffix: str, overwrite: bool = False) -> Path:
    """Pick the output path.

    - `output` is a directory -> <output>/<stem><suffix>
    - `output` is a file path -> used as-is
    - no `output` -> <src dir>/<stem>.min<suffix>
    """
    if output is None:
        dst = src.with_name(f"{src.stem}.min{suffix}")
    elif output.is_dir():
        dst = output / f"{src.stem}{suffix}"
    else:
        dst = output
    if dst.resolve() == src.resolve():
        raise ValueError(f"Output would overwrite the input file: {src}")
    if dst.exists() and not overwrite:
        raise FileExistsError(f"Output already exists (use --overwrite): {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    return dst
