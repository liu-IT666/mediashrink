"""Video transcoding / compression via ffmpeg."""

from dataclasses import dataclass
from pathlib import Path

from mediashrink import ffmpeg

# codec name -> (ffmpeg encoder, default CRF)
VIDEO_CODECS = {
    "h264": ("libx264", 23),
    "h265": ("libx265", 28),
    "av1": ("libsvtav1", 35),
    "vp9": ("libvpx-vp9", 33),
}

# container -> codecs it can hold (checked against ffmpeg; av1 in .mov hangs ffmpeg 6.x)
CONTAINER_CODECS = {
    ".mp4": {"h264", "h265", "av1", "vp9"},
    ".mov": {"h264", "h265"},
    ".mkv": {"h264", "h265", "av1", "vp9"},
    ".webm": {"av1", "vp9"},
}

# x264/x265 preset name -> (svt-av1 --preset 0..12, libvpx-vp9 -cpu-used 0..5); higher = faster
PRESETS = {
    "ultrafast": (12, 5),
    "superfast": (11, 5),
    "veryfast": (10, 4),
    "faster": (9, 4),
    "fast": (9, 3),
    "medium": (8, 2),
    "slow": (6, 1),
    "slower": (4, 0),
    "veryslow": (2, 0),
    "placebo": (0, 0),
}


@dataclass
class VideoOptions:
    codec: str = "h265"
    crf: int | None = None
    preset: str = "medium"
    max_height: int | None = None
    fps: float | None = None
    audio_bitrate: str = "128k"
    strip_audio: bool = False


def build_args(src: Path, dst: Path, opts: VideoOptions) -> list[str]:
    if opts.codec not in VIDEO_CODECS:
        raise ValueError(f"Unknown codec {opts.codec!r}; choose from {', '.join(VIDEO_CODECS)}")
    ext = dst.suffix.lower()
    if ext not in CONTAINER_CODECS:
        raise ValueError(f"Unsupported container {ext!r}; choose from {', '.join(CONTAINER_CODECS)}")
    if opts.codec not in CONTAINER_CODECS[ext]:
        fits = ", ".join(c for c, codecs in CONTAINER_CODECS.items() if opts.codec in codecs)
        raise ValueError(f"{opts.codec} cannot be stored in {ext}; use one of: {fits}")
    if opts.preset not in PRESETS:
        raise ValueError(f"Unknown preset {opts.preset!r}; choose from {', '.join(PRESETS)}")
    encoder, default_crf = VIDEO_CODECS[opts.codec]
    crf = opts.crf if opts.crf is not None else default_crf
    av1_preset, vp9_cpu_used = PRESETS[opts.preset]

    args = ["-y", "-i", str(src), "-map_metadata", "0", "-c:v", encoder, "-crf", str(crf)]
    if opts.codec == "vp9":
        # constant-quality mode; libvpx has no named presets, -cpu-used trades speed for quality
        args += ["-b:v", "0", "-deadline", "good", "-cpu-used", str(vp9_cpu_used)]
    elif opts.codec == "av1":
        args += ["-preset", str(av1_preset)]  # svt-av1 uses numeric presets
    else:
        args += ["-preset", opts.preset]
    if opts.codec == "h265" and ext in {".mp4", ".mov"}:
        args += ["-tag:v", "hvc1"]  # so QuickTime / Apple devices can play it

    filters = []
    if opts.max_height:
        # Only downscale; keep width even for yuv420p.
        filters.append(f"scale=-2:'min({opts.max_height},ih)'")
    if filters:
        args += ["-vf", ",".join(filters)]
    if opts.fps:
        args += ["-r", str(opts.fps)]
    args += ["-pix_fmt", "yuv420p"]

    if opts.strip_audio:
        args += ["-an"]
    else:
        audio_codec = "libopus" if ext == ".webm" else "aac"
        args += ["-c:a", audio_codec, "-b:a", opts.audio_bitrate]

    if ext in {".mp4", ".mov"}:
        args += ["-movflags", "+faststart"]
    args.append(str(dst))
    return args


def compress(src: Path, dst: Path, opts: VideoOptions) -> None:
    ffmpeg.run(build_args(src, dst, opts))
