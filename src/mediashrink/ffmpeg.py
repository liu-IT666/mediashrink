"""Thin wrapper around the ffmpeg / ffprobe binaries."""

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

Progress = Callable[[float], None]  # called with the fraction done, 0.0 .. 1.0


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


@dataclass(frozen=True)
class AudioStream:
    codec: str
    bit_rate: int | None  # bits/s; None when the container does not say


def probe_audio(path: Path) -> AudioStream | None:
    """The audio stream ffmpeg picks by default (most channels, first on ties), or None.

    For audio-only files whose stream has no bit_rate (e.g. Opus in Ogg), the file's
    overall bit rate is used instead.
    """
    try:
        info = probe(path)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    streams = info.get("streams", [])
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if not audio:
        return None
    best = max(audio, key=lambda s: s.get("channels", 0))  # max() keeps the first on ties
    rate = best.get("bit_rate") or (info.get("format", {}).get("bit_rate") if len(streams) == 1 else None)
    return AudioStream(best.get("codec_name", ""), int(rate) if rate and str(rate).isdigit() else None)


def duration(path: Path) -> float | None:
    """Container duration in seconds, or None if ffprobe cannot tell."""
    try:
        return float(probe(path)["format"]["duration"])
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError):
        return None


def parse_bitrate(value: str) -> int | None:
    """'128k' -> 128000, '1.5M' -> 1500000, '96000' -> 96000; None if unparsable."""
    units = {"k": 1_000, "m": 1_000_000}
    v = value.strip().lower()
    mult = units.get(v[-1:], 1)
    try:
        n = float(v[:-1] if mult > 1 else v)
    except ValueError:
        return None
    return int(n * mult) if n > 0 else None


# Encoders overshoot their target a little (a "64k" AAC stream reports ~65 kb/s).
BITRATE_TOLERANCE = 1.05


def audio_is_small_enough(stream: AudioStream | None, codecs: set[str], target: str) -> bool:
    """Re-encoding would cost quality without saving space: the codec already fits the
    output and its bit rate is at or below `target`."""
    limit = parse_bitrate(target)
    return (
        stream is not None
        and stream.codec in codecs
        and stream.bit_rate is not None
        and limit is not None
        and stream.bit_rate <= limit * BITRATE_TOLERANCE
    )


def metadata_args(strip: bool) -> list[str]:
    """Container-level tags (GPS location, device, creation time, title...) are dropped when
    `strip`; per-stream tags such as audio language are kept either way."""
    return ["-map_metadata:g", "-1"] if strip else ["-map_metadata", "0"]


def run(args: list[str], total: float | None = None, progress: Progress | None = None) -> None:
    """Run ffmpeg with the given args (input/output included).

    With `progress` and the input's duration `total` (seconds), ffmpeg's `-progress`
    output is parsed and `progress` is called with the fraction of the input encoded.
    """
    cmd = [_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin"]
    if progress is None or not total:
        proc = subprocess.run([*cmd, *args], capture_output=True, text=True)
        stderr = proc.stderr
    else:
        # stderr goes to a file so a chatty ffmpeg can never block on a full pipe while we read stdout
        with tempfile.TemporaryFile("w+") as err:
            with subprocess.Popen(
                [*cmd, "-progress", "pipe:1", "-nostats", *args], stdout=subprocess.PIPE, stderr=err, text=True
            ) as proc:
                assert proc.stdout is not None
                for line in proc.stdout:
                    key, _, value = line.strip().partition("=")
                    if key == "out_time_us" and value.isdigit():
                        progress(min(int(value) / 1e6 / total, 1.0))
            err.seek(0)
            stderr = err.read()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{stderr.strip()}")
