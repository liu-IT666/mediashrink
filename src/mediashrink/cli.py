"""Command-line interface."""

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import pikepdf
import typer
from rich.console import Console

from mediashrink import audio, ffmpeg, image, pdf, video
from mediashrink.common import Result, atomic_output, human_size, output_path, resolve_output

app = typer.Typer(
    help="Transcode and shrink video, audio, image and PDF files.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

Inputs = Annotated[list[Path], typer.Argument(exists=True, dir_okay=False, help="Input file(s).")]
Output = Annotated[
    Path | None,
    typer.Option("--output", "-o", help="Output file, or directory for multiple inputs. Default: <name>.min.<ext>"),
]
Overwrite = Annotated[bool, typer.Option("--overwrite", "-y", help="Overwrite existing output files.")]
KeepLarger = Annotated[
    bool, typer.Option("--keep-larger", help="Keep the output even if it is not smaller than the input.")
]

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".wmv"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".gif"}


def _process(
    inputs: list[Path],
    output: Path | None,
    overwrite: bool,
    suffix_for: Callable[[Path], str],
    action: Callable[[Path, Path], None],
    keep_larger: bool = False,
) -> None:
    if len(inputs) > 1 and output is not None and not output.is_dir():
        raise typer.BadParameter("With multiple inputs, --output must be an existing directory.")
    failed = 0
    claimed: dict[Path, Path] = {}  # resolved output -> input that wrote it in this run
    for src in inputs:
        try:
            suffix = suffix_for(src)
            key = output_path(src, output, suffix).resolve()
            if key in claimed:  # e.g. a.png and a.jpg both -> a.min.jpg
                raise ValueError(f"same output as {claimed[key].name}: {key.name}; use separate runs or --output")
            dst = resolve_output(src, output, suffix, overwrite)
            with atomic_output(dst) as tmp:
                with console.status(f"Processing {src.name}..."):
                    action(src, tmp)
                src_size, out_size = src.stat().st_size, tmp.stat().st_size
                discard = out_size >= src_size and not keep_larger
                if discard:
                    tmp.unlink()  # atomic_output then leaves dst untouched
            if discard:
                console.print(
                    f"[yellow]–[/] {src.name}: output not smaller ({human_size(src_size)} → {human_size(out_size)}), "
                    "discarded (use --keep-larger to keep it)"
                )
                continue
            claimed[key] = src
            r = Result(src, dst)
            color = "green" if r.ratio < 1 else "yellow"
            console.print(
                f"[{color}]✓[/] {src.name} → {dst.name}  "
                f"{human_size(r.src_size)} → {human_size(r.dst_size)} ([{color}]{r.ratio:.0%}[/])"
            )
        except (ValueError, FileExistsError, RuntimeError, OSError, pikepdf.PdfError) as e:
            failed += 1
            console.print(f"[red]✗ {src.name}: {e}")
    if failed:
        raise typer.Exit(1)


def _ext(fmt: str | None, default: Callable[[Path], str]) -> Callable[[Path], str]:
    if fmt:
        suffix = "." + fmt.lower().lstrip(".")
        return lambda _src: suffix
    return default


@app.command("video")
def video_cmd(
    inputs: Inputs,
    output: Output = None,
    overwrite: Overwrite = False,
    keep_larger: KeepLarger = False,
    fmt: Annotated[str | None, typer.Option("--format", "-f", help="Container: mp4, mkv, webm, mov.")] = None,
    codec: Annotated[str, typer.Option("--codec", "-c", help=f"One of: {', '.join(video.VIDEO_CODECS)}.")] = "h265",
    crf: Annotated[int | None, typer.Option(help="Quality (lower = better/bigger). Default depends on codec.")] = None,
    preset: Annotated[
        str, typer.Option(help="Speed preset (ultrafast … veryslow); mapped onto av1/vp9 speed settings.")
    ] = "medium",
    max_height: Annotated[
        int | None, typer.Option("--max-height", help="Downscale to at most this height, e.g. 1080.")
    ] = None,
    fps: Annotated[float | None, typer.Option(help="Output frame rate.")] = None,
    audio_bitrate: Annotated[str, typer.Option("--audio-bitrate", help="e.g. 96k, 128k.")] = "128k",
    no_audio: Annotated[bool, typer.Option("--no-audio", help="Drop the audio track.")] = False,
) -> None:
    """Transcode / compress video files."""
    opts = video.VideoOptions(codec, crf, preset, max_height, fps, audio_bitrate, no_audio)
    default = ".webm" if codec == "vp9" else ".mp4"
    _process(
        inputs, output, overwrite, _ext(fmt, lambda _s: default), lambda s, d: video.compress(s, d, opts), keep_larger
    )


@app.command("audio")
def audio_cmd(
    inputs: Inputs,
    output: Output = None,
    overwrite: Overwrite = False,
    keep_larger: KeepLarger = False,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help=f"One of: {', '.join(e[1:] for e in audio.AUDIO_FORMATS)}.")
    ] = "m4a",
    bitrate: Annotated[str, typer.Option("--bitrate", "-b", help="e.g. 64k, 128k, 192k.")] = "128k",
    sample_rate: Annotated[int | None, typer.Option("--sample-rate", help="e.g. 44100, 22050.")] = None,
    mono: Annotated[bool, typer.Option(help="Downmix to mono.")] = False,
) -> None:
    """Transcode / compress audio files."""
    opts = audio.AudioOptions(bitrate, sample_rate, mono)
    _process(
        inputs, output, overwrite, _ext(fmt, lambda s: s.suffix), lambda s, d: audio.compress(s, d, opts), keep_larger
    )


@app.command("image")
def image_cmd(
    inputs: Inputs,
    output: Output = None,
    overwrite: Overwrite = False,
    keep_larger: KeepLarger = False,
    fmt: Annotated[
        str | None, typer.Option("--format", "-f", help="jpg, png, webp, avif. Default: keep / webp for GIF / jpg.")
    ] = None,
    quality: Annotated[int, typer.Option("--quality", "-q", min=1, max=100)] = 80,
    max_size: Annotated[int | None, typer.Option("--max-size", help="Longest edge in px, e.g. 1920.")] = None,
    keep_metadata: Annotated[bool, typer.Option("--keep-metadata", help="Keep EXIF data.")] = False,
) -> None:
    """Convert / compress image files."""
    opts = image.ImageOptions(quality, max_size, not keep_metadata)
    _process(
        inputs, output, overwrite, _ext(fmt, image.default_suffix), lambda s, d: image.compress(s, d, opts), keep_larger
    )


@app.command("pdf")
def pdf_cmd(
    inputs: Inputs,
    output: Output = None,
    overwrite: Overwrite = False,
    keep_larger: KeepLarger = False,
    image_quality: Annotated[int, typer.Option("--image-quality", "-q", min=1, max=100)] = 70,
    max_image_size: Annotated[
        int | None, typer.Option("--max-image-size", help="Longest edge of embedded images, px.")
    ] = 2000,
) -> None:
    """Compress PDF files (recompress embedded images and streams)."""
    opts = pdf.PdfOptions(image_quality, max_image_size)
    _process(inputs, output, overwrite, lambda _s: ".pdf", lambda s, d: pdf.compress(s, d, opts), keep_larger)


@app.command("auto")
def auto_cmd(
    inputs: Inputs, output: Output = None, overwrite: Overwrite = False, keep_larger: KeepLarger = False
) -> None:
    """Compress files with default settings, picking the handler by file extension."""

    def suffix(src: Path) -> str:
        ext = src.suffix.lower()
        if ext in VIDEO_EXTS:
            return ".mp4"
        if ext in AUDIO_EXTS:
            return ".m4a" if ext in {".wav", ".wma", ".flac"} else ext
        if ext in IMAGE_EXTS:
            return image.default_suffix(src)
        if ext == ".pdf":
            return ".pdf"
        raise ValueError(f"Unsupported file type: {ext}")

    def action(src: Path, dst: Path) -> None:
        ext = src.suffix.lower()
        if ext in VIDEO_EXTS:
            video.compress(src, dst, video.VideoOptions())
        elif ext in AUDIO_EXTS:
            audio.compress(src, dst, audio.AudioOptions())
        elif ext in IMAGE_EXTS:
            image.compress(src, dst, image.ImageOptions())
        else:
            pdf.compress(src, dst, pdf.PdfOptions())

    _process(inputs, output, overwrite, suffix, action, keep_larger)


@app.command("info")
def info_cmd(path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Show media info (ffprobe) for a video / audio file."""
    try:
        info = ffmpeg.probe(path)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ {path.name}: ffprobe failed: {e.stderr.strip()}")
        raise typer.Exit(1) from None
    except ffmpeg.FFmpegNotFound as e:
        console.print(f"[red]✗ {e}")
        raise typer.Exit(1) from None
    console.print_json(json.dumps(info))
