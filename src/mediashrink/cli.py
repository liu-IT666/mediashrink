"""Command-line interface."""

import json
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import pikepdf
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

from mediashrink import audio, ffmpeg, image, pdf, video
from mediashrink.common import (
    Result,
    atomic_output,
    collect_inputs,
    human_size,
    is_dir_target,
    output_path,
    resolve_output,
)

app = typer.Typer(
    help="Transcode and shrink video, audio, image and PDF files.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

Inputs = Annotated[
    list[Path],
    typer.Argument(exists=True, help="Input file(s) or directories (files with a matching extension inside)."),
]
Output = Annotated[
    Path | None,
    typer.Option(
        "--output",
        "-o",
        help="Output file, or directory (created if missing). Default: <name>.min.<ext> next to input.",
    ),
]
Overwrite = Annotated[bool, typer.Option("--overwrite", "-y", help="Overwrite existing output files.")]
KeepMetadata = Annotated[
    bool, typer.Option("--keep-metadata", help="Keep metadata (GPS location, device, dates, tags...).")
]
KeepLarger = Annotated[
    bool, typer.Option("--keep-larger", help="Keep the output even if it is not smaller than the input.")
]
Recursive = Annotated[
    bool, typer.Option("--recursive", "-r", help="Also take files in subdirectories of directory inputs.")
]
Jobs = Annotated[int, typer.Option("--jobs", "-j", min=1, help="Number of files to process in parallel.")]

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".flv", ".wmv"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".gif"}


# (src, temp dst, progress callback) -> None; the callback takes the fraction done, 0..1
Action = Callable[[Path, Path, ffmpeg.Progress], None]


@dataclass
class Item:
    src: Path
    subdir: Path  # relative directory inside a directory input, mirrored under a directory --output


@dataclass
class Outcome:
    status: str  # "ok" | "discarded" | "failed"
    src_size: int = 0
    dst_size: int = 0


def _process(
    inputs: list[Path],
    output: Path | None,
    overwrite: bool,
    suffix_for: Callable[[Path], str],
    action: Action,
    exts: set[str],
    keep_larger: bool = False,
    recursive: bool = False,
    jobs: int = 1,
) -> None:
    has_dir = any(p.is_dir() for p in inputs)
    out_dir = output if output is not None and is_dir_target(output) else None
    items = [Item(src, sub) for src, sub in collect_inputs(inputs, exts, recursive, exclude=out_dir)]
    if (len(items) > 1 or has_dir) and output is not None and out_dir is None:
        raise typer.BadParameter("With multiple inputs or a directory input, --output must be a directory.")
    if not items:
        raise typer.BadParameter(f"No files with a supported extension ({', '.join(sorted(exts))}) in the input.")

    outcomes: list[Outcome] = []
    # Inputs that map to the same output run one after another in one group: the first that
    # writes it claims it, the rest fail (e.g. a.png and a.jpg both -> a.min.jpg).
    groups: dict[Path, list[Item]] = {}
    for item in items:
        try:
            key = output_path(item.src, output, suffix_for(item.src), item.subdir).resolve()
        except ValueError as e:
            outcomes.append(_fail(item.src, e))
            continue
        groups.setdefault(key, []).append(item)

    columns = (
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    )
    # Bars only on a terminal; piped or captured output gets just the result lines.
    with Progress(*columns, console=console, transient=True, disable=not console.is_terminal) as bar:

        def run_group(group: list[Item]) -> list[Outcome]:
            done, claimed_by = [], None
            for item in group:
                if claimed_by is not None:
                    name = output_path(item.src, output, suffix_for(item.src), item.subdir).name
                    err = ValueError(f"same output as {claimed_by.name}: {name}; use separate runs or --output")
                    done.append(_fail(item.src, err))
                    continue
                done.append(_one(item, output, overwrite, suffix_for, action, keep_larger, bar))
                if done[-1].status == "ok":
                    claimed_by = item.src
            return done

        if jobs == 1:
            for group in groups.values():
                outcomes += run_group(group)
        else:
            pool = ThreadPoolExecutor(max_workers=jobs)
            try:
                for future in as_completed([pool.submit(run_group, g) for g in groups.values()]):
                    outcomes += future.result()
            finally:
                pool.shutdown(cancel_futures=True)  # on Ctrl+C, do not start the files still queued

    if len(outcomes) > 1:
        _summary(outcomes)
    if any(o.status == "failed" for o in outcomes):
        raise typer.Exit(1)


def _fail(src: Path, e: Exception) -> Outcome:
    console.print(f"[red]✗ {src.name}: {e}")
    return Outcome("failed")


def _one(
    item: Item,
    output: Path | None,
    overwrite: bool,
    suffix_for: Callable[[Path], str],
    action: Action,
    keep_larger: bool,
    bar: Progress,
) -> Outcome:
    src = item.src
    task = bar.add_task(src.name, total=None)  # indeterminate until the handler reports progress
    try:
        dst = resolve_output(src, output, suffix_for(src), overwrite, item.subdir)
        with atomic_output(dst) as tmp:
            action(src, tmp, lambda done: bar.update(task, total=1.0, completed=done))
            src_size, out_size = src.stat().st_size, tmp.stat().st_size
            discard = out_size >= src_size and not keep_larger
            if discard:
                tmp.unlink()  # atomic_output then leaves dst untouched
    except (ValueError, FileExistsError, RuntimeError, OSError, pikepdf.PdfError) as e:
        return _fail(src, e)
    finally:
        bar.remove_task(task)
    if discard:
        console.print(
            f"[yellow]–[/] {src.name}: output not smaller ({human_size(src_size)} → {human_size(out_size)}), "
            "discarded (use --keep-larger to keep it)"
        )
        return Outcome("discarded", src_size, src_size)
    r = Result(src, dst)
    color = "green" if r.ratio < 1 else "yellow"
    console.print(
        f"[{color}]✓[/] {src.name} → {dst.name}  "
        f"{human_size(r.src_size)} → {human_size(r.dst_size)} ([{color}]{r.ratio:.0%}[/])"
    )
    return Outcome("ok", r.src_size, r.dst_size)


def _summary(outcomes: list[Outcome]) -> None:
    """One line for a batch: counts, plus total size before / after over the files written."""
    ok = [o for o in outcomes if o.status == "ok"]
    discarded = sum(o.status == "discarded" for o in outcomes)
    failed = sum(o.status == "failed" for o in outcomes)
    parts = [f"{len(ok)} compressed"]
    if discarded:
        parts.append(f"{discarded} discarded")
    if failed:
        parts.append(f"[red]{failed} failed[/]")
    line = f"[bold]{len(outcomes)} files:[/] " + ", ".join(parts)
    before, after = sum(o.src_size for o in ok), sum(o.dst_size for o in ok)
    if before:
        line += (
            f"  {human_size(before)} → {human_size(after)} ({after / before:.0%}), saved {human_size(before - after)}"
        )
    console.print(line)


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
    recursive: Recursive = False,
    jobs: Jobs = 1,
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
    keep_metadata: KeepMetadata = False,
) -> None:
    """Transcode / compress video files."""
    opts = video.VideoOptions(codec, crf, preset, max_height, fps, audio_bitrate, no_audio, not keep_metadata)
    default = ".webm" if codec == "vp9" else ".mp4"
    _process(
        inputs,
        output,
        overwrite,
        _ext(fmt, lambda _s: default),
        lambda s, d, p: video.compress(s, d, opts, p),
        VIDEO_EXTS,
        keep_larger,
        recursive,
        jobs,
    )


@app.command("audio")
def audio_cmd(
    inputs: Inputs,
    output: Output = None,
    overwrite: Overwrite = False,
    keep_larger: KeepLarger = False,
    recursive: Recursive = False,
    jobs: Jobs = 1,
    fmt: Annotated[
        str, typer.Option("--format", "-f", help=f"One of: {', '.join(e[1:] for e in audio.AUDIO_FORMATS)}.")
    ] = "m4a",
    bitrate: Annotated[str, typer.Option("--bitrate", "-b", help="e.g. 64k, 128k, 192k.")] = "128k",
    sample_rate: Annotated[int | None, typer.Option("--sample-rate", help="e.g. 44100, 22050.")] = None,
    mono: Annotated[bool, typer.Option(help="Downmix to mono.")] = False,
    keep_metadata: KeepMetadata = False,
) -> None:
    """Transcode / compress audio files."""
    opts = audio.AudioOptions(bitrate, sample_rate, mono, not keep_metadata)
    _process(
        inputs,
        output,
        overwrite,
        _ext(fmt, lambda s: s.suffix),
        lambda s, d, p: audio.compress(s, d, opts, p),
        AUDIO_EXTS,
        keep_larger,
        recursive,
        jobs,
    )


@app.command("image")
def image_cmd(
    inputs: Inputs,
    output: Output = None,
    overwrite: Overwrite = False,
    keep_larger: KeepLarger = False,
    recursive: Recursive = False,
    jobs: Jobs = 1,
    fmt: Annotated[
        str | None, typer.Option("--format", "-f", help="jpg, png, webp, avif. Default: keep / webp for GIF / jpg.")
    ] = None,
    quality: Annotated[int, typer.Option("--quality", "-q", min=1, max=100)] = 80,
    max_size: Annotated[int | None, typer.Option("--max-size", help="Longest edge in px, e.g. 1920.")] = None,
    keep_metadata: KeepMetadata = False,
) -> None:
    """Convert / compress image files."""
    opts = image.ImageOptions(quality, max_size, not keep_metadata)
    _process(
        inputs,
        output,
        overwrite,
        _ext(fmt, image.default_suffix),
        lambda s, d, _p: image.compress(s, d, opts),
        IMAGE_EXTS,
        keep_larger,
        recursive,
        jobs,
    )


@app.command("pdf")
def pdf_cmd(
    inputs: Inputs,
    output: Output = None,
    overwrite: Overwrite = False,
    keep_larger: KeepLarger = False,
    recursive: Recursive = False,
    jobs: Jobs = 1,
    image_quality: Annotated[int, typer.Option("--image-quality", "-q", min=1, max=100)] = 70,
    max_image_size: Annotated[
        int | None, typer.Option("--max-image-size", help="Longest edge of embedded images, px.")
    ] = 2000,
) -> None:
    """Compress PDF files (recompress embedded images and streams)."""
    opts = pdf.PdfOptions(image_quality, max_image_size)
    _process(
        inputs,
        output,
        overwrite,
        lambda _s: ".pdf",
        lambda s, d, _p: pdf.compress(s, d, opts),
        {".pdf"},
        keep_larger,
        recursive,
        jobs,
    )


@app.command("auto")
def auto_cmd(
    inputs: Inputs,
    output: Output = None,
    overwrite: Overwrite = False,
    keep_larger: KeepLarger = False,
    recursive: Recursive = False,
    jobs: Jobs = 1,
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

    def action(src: Path, dst: Path, progress: ffmpeg.Progress) -> None:
        ext = src.suffix.lower()
        if ext in VIDEO_EXTS:
            video.compress(src, dst, video.VideoOptions(), progress)
        elif ext in AUDIO_EXTS:
            audio.compress(src, dst, audio.AudioOptions(), progress)
        elif ext in IMAGE_EXTS:
            image.compress(src, dst, image.ImageOptions())
        else:
            pdf.compress(src, dst, pdf.PdfOptions())

    exts = VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS | {".pdf"}
    _process(inputs, output, overwrite, suffix, action, exts, keep_larger, recursive, jobs)


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
