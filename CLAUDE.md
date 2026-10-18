# mediashrink

Python CLI for transcoding and shrinking video, audio, image and PDF files.

## Commands
- Install / sync deps: `uv sync`
- Run the CLI: `uv run mediashrink --help`
- Tests: `uv run pytest`
- Lint / format: `uv run ruff check . && uv run ruff format .`

## Layout
- `src/mediashrink/cli.py` — Typer app; one subcommand per media type plus `auto` and `info`. `_process()` handles output paths, batch inputs and the size report; it writes through `common.atomic_output()` (temp file, renamed on success) and discards outputs that are not smaller unless `--keep-larger`.
- `video.py` / `audio.py` — build ffmpeg argument lists (`build_args`) and run them through `ffmpeg.py`. Keep arg-building pure so it can be unit-tested without ffmpeg. `build_args` validates options up front so bad combinations fail before ffmpeg runs. `video.CONTAINER_CODECS` lists which codecs each container accepts (verified against ffmpeg); `video.PRESETS` maps x264-style preset names onto svt-av1 / libvpx-vp9 speed settings.
- `image.py` — Pillow (JPEG/PNG/WebP/AVIF out; HEIC/HEIF in via `pillow-heif`). Animated GIF/APNG/WebP/AVIF inputs keep all frames when the output format can hold them.
- `ffmpeg.py` — runs `ffmpeg` / `ffprobe`; `metadata_args()` is the shared metadata policy (strip container-level tags such as GPS, keep per-stream tags such as language).
- `pdf.py` — pikepdf; re-encodes embedded RGB/gray/indexed images as JPEG (skips images with an SMask, CMYK, 1-/16-bit, and any that would not shrink) and recompresses streams. `page.get_images()` already descends into Form XObjects. Ghostscript is intentionally not a dependency.
- `common.py` — output paths: `output_path()` (pure; `<name>.min.<ext>` by default; an extensionless missing `-o` is a directory, see `is_dir_target()`), `resolve_output()` (adds the checks: never the input, no overwrite without `-y`), `atomic_output()` (temp `.part-<name>` file, renamed on success, removed on error).

## Conventions
- External binaries: only `ffmpeg` / `ffprobe` (must be on PATH). Tests that need them use `requires_ffmpeg` from `tests/conftest.py`.
- Each module exposes an `*Options` dataclass plus `compress(src, dst, opts)`. `compress` writes to whatever `dst` it gets (in practice a temp path), so it must take the format from `dst.suffix`, never from the final name.
- Errors: raise `ValueError` for bad input/options and `RuntimeError` for encoder failures. `_process()` catches only a fixed tuple (plus `OSError`, `FileExistsError`, `pikepdf.PdfError`); if a handler can raise another exception type, add it there, or one bad file aborts the whole batch.
- Privacy defaults: metadata (EXIF, GPS, container tags) is stripped unless `--keep-metadata`; image ICC profiles are always kept.
- Claims about ffmpeg / Pillow / pikepdf behavior (supported combinations, what a reader returns) are verified by running them, and pinned by tests; README.md (Chinese) documents user-facing defaults, so update it when a default changes.
