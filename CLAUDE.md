# mediashrink

Python CLI for transcoding and shrinking video, audio, image and PDF files.

## Commands
- Install / sync deps: `uv sync`
- Run the CLI: `uv run mediashrink --help`
- Tests: `uv run pytest`
- Lint / format: `uv run ruff check . && uv run ruff format .`

## Layout
- `src/mediashrink/cli.py` — Typer app; one subcommand per media type plus `auto` and `info`. `_process()` handles output paths, batch inputs and the size report; it writes through `common.atomic_output()` (temp file, renamed on success) and discards outputs that are not smaller unless `--keep-larger`.
- `video.py` / `audio.py` — build ffmpeg argument lists (`build_args`) and run them through `ffmpeg.py`. Keep arg-building pure so it can be unit-tested without ffmpeg.
- `image.py` — Pillow (JPEG/PNG/WebP/AVIF).
- `pdf.py` — pikepdf; re-encodes embedded RGB/gray images as JPEG and recompresses streams. Ghostscript is intentionally not a dependency.
- `common.py` — output path resolution (`<name>.min.<ext>` by default, never overwrites the input).

## Conventions
- External binaries: only `ffmpeg` / `ffprobe` (must be on PATH). Tests that need them use `requires_ffmpeg` from `tests/conftest.py`.
- Each module exposes an `*Options` dataclass plus `compress(src, dst, opts)`.
