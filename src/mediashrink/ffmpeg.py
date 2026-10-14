"""Thin wrapper around the ffmpeg / ffprobe binaries."""

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegNotFound(RuntimeError):
    pass


def _bin(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FFmpegNotFound(f"`{name}` not found on PATH. Install it, e.g. `brew install ffmpeg`.")
    return path


def probe(path: Path) -> dict:
    out = subprocess.run(
        [_bin("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def run(args: list[str]) -> None:
    """Run ffmpeg with the given args (input/output included)."""
    proc = subprocess.run(
        [_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr.strip()}")
