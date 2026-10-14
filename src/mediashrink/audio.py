"""Audio transcoding / compression via ffmpeg."""

from dataclasses import dataclass
from pathlib import Path

from mediashrink import ffmpeg

# output format -> ffmpeg encoder
AUDIO_FORMATS = {
    ".mp3": "libmp3lame",
    ".m4a": "aac",
    ".aac": "aac",
    ".opus": "libopus",
    ".ogg": "libvorbis",
    ".flac": "flac",
}


@dataclass
class AudioOptions:
    bitrate: str = "128k"
    sample_rate: int | None = None
    mono: bool = False


def build_args(src: Path, dst: Path, opts: AudioOptions) -> list[str]:
    ext = dst.suffix.lower()
    if ext not in AUDIO_FORMATS:
        raise ValueError(f"Unsupported audio format {ext!r}; choose from {', '.join(AUDIO_FORMATS)}")
    args = ["-y", "-i", str(src), "-vn", "-map_metadata", "0", "-c:a", AUDIO_FORMATS[ext]]
    if ext != ".flac":  # flac is lossless; bitrate does not apply
        args += ["-b:a", opts.bitrate]
    if opts.sample_rate:
        args += ["-ar", str(opts.sample_rate)]
    if opts.mono:
        args += ["-ac", "1"]
    args.append(str(dst))
    return args


def compress(src: Path, dst: Path, opts: AudioOptions) -> None:
    ffmpeg.run(build_args(src, dst, opts))
