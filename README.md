# mediashrink

A command-line tool that transcodes and compresses **video, audio, image and PDF** files.

## Requirements
- Python ≥ 3.12, [uv](https://docs.astral.sh/uv/)
- [ffmpeg](https://ffmpeg.org/) on PATH (for video / audio): `brew install ffmpeg`

## Install
```bash
uv sync
uv tool install .   # optional: install `mediashrink` globally
```

## Usage
```bash
mediashrink auto clip.mov photo.png doc.pdf             # default settings, by file type
mediashrink video in.mov -c h265 --crf 28 --max-height 1080
mediashrink video in.mp4 -c av1 -f mkv -o out/
mediashrink audio song.wav -f mp3 -b 192k
mediashrink image *.png -f webp -q 75 --max-size 1920 -o out/
mediashrink pdf scan.pdf -q 60 --max-image-size 1600
mediashrink info in.mp4
```
By default, output is written next to the input as `<name>.min.<ext>`. Existing files are never overwritten unless you pass `-y`.
If a result is not smaller than its input it is discarded; pass `--keep-larger` to keep it anyway (e.g. for a format conversion). A failed or interrupted run never leaves a partial output file behind.

## Development
```bash
uv run pytest
uv run ruff check . && uv run ruff format .
```
