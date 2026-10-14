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
    encoder, default_crf = VIDEO_CODECS[opts.codec]
    crf = opts.crf if opts.crf is not None else default_crf

    args = ["-y", "-i", str(src), "-map_metadata", "0", "-c:v", encoder, "-crf", str(crf)]
    if opts.codec == "vp9":
        args += ["-b:v", "0"]  # constant-quality mode for libvpx-vp9
    elif opts.codec == "av1":
        args += ["-preset", "8"]  # svt-av1 uses numeric presets
    else:
        args += ["-preset", opts.preset]
    if opts.codec == "h265" and dst.suffix.lower() in {".mp4", ".mov"}:
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
        audio_codec = "libopus" if dst.suffix.lower() == ".webm" else "aac"
        args += ["-c:a", audio_codec, "-b:a", opts.audio_bitrate]

    if dst.suffix.lower() in {".mp4", ".mov"}:
        args += ["-movflags", "+faststart"]
    args.append(str(dst))
    return args


def compress(src: Path, dst: Path, opts: VideoOptions) -> None:
    ffmpeg.run(build_args(src, dst, opts))
