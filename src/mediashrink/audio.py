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

# output format -> codec (ffprobe name) that is copied as-is when already small enough.
# flac is lossless, so re-encoding it is never a quality loss and may still shrink it.
COPYABLE = {".mp3": "mp3", ".m4a": "aac", ".aac": "aac", ".opus": "opus", ".ogg": "vorbis"}


@dataclass
class AudioOptions:
    bitrate: str = "128k"
    sample_rate: int | None = None
    mono: bool = False
    strip_metadata: bool = True  # see ffmpeg.metadata_args; drops ID3 / Vorbis tags too


def build_args(src: Path, dst: Path, opts: AudioOptions, src_audio: ffmpeg.AudioStream | None = None) -> list[str]:
    """`src_audio` is the input's audio stream (from `ffmpeg.probe_audio`); when it is
    already in the output codec at or below `bitrate` and nothing else changes, it is
    copied instead of re-encoded (only the metadata changes)."""
    ext = dst.suffix.lower()
    if ext not in AUDIO_FORMATS:
        raise ValueError(f"Unsupported audio format {ext!r}; choose from {', '.join(AUDIO_FORMATS)}")
    args = ["-y", "-i", str(src), "-vn", *ffmpeg.metadata_args(opts.strip_metadata)]
    copyable = {COPYABLE[ext]} if ext in COPYABLE else set()
    if not opts.sample_rate and not opts.mono and ffmpeg.audio_is_small_enough(src_audio, copyable, opts.bitrate):
        return [*args, "-c:a", "copy", str(dst)]
    args += ["-c:a", AUDIO_FORMATS[ext]]
    if ext != ".flac":  # flac is lossless; bitrate does not apply
        args += ["-b:a", opts.bitrate]
    if opts.sample_rate:
        args += ["-ar", str(opts.sample_rate)]
    if opts.mono:
        args += ["-ac", "1"]
    args.append(str(dst))
    return args


def compress(src: Path, dst: Path, opts: AudioOptions, progress: ffmpeg.Progress | None = None) -> None:
    build_args(src, dst, opts)  # validate options before probing
    args = build_args(src, dst, opts, ffmpeg.probe_audio(src))
    ffmpeg.run(args, ffmpeg.duration(src) if progress else None, progress)
