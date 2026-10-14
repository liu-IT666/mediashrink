from pathlib import Path

from PIL import Image

from mediashrink.image import ImageOptions, compress


def _make_png(path: Path, size=(1600, 1200)) -> Path:
    Image.effect_noise(size, 64).convert("RGB").save(path)
    return path


def test_png_to_jpg_shrinks(tmp_path: Path):
    src = _make_png(tmp_path / "a.png")
    dst = tmp_path / "a.jpg"
    compress(src, dst, ImageOptions(quality=70))
    assert dst.stat().st_size < src.stat().st_size


def test_max_size(tmp_path: Path):
    src = _make_png(tmp_path / "a.png")
    dst = tmp_path / "a.webp"
    compress(src, dst, ImageOptions(max_size=800))
    with Image.open(dst) as im:
        assert max(im.size) == 800
