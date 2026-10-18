from pathlib import Path

from PIL import Image, ImageCms

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


def _srgb_icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def test_icc_profile_kept_when_stripping_exif(tmp_path: Path):
    src = tmp_path / "a.jpg"
    exif = Image.Exif()
    exif[0x010F] = "TestCam"  # Make
    Image.new("RGB", (64, 64), "red").save(src, icc_profile=_srgb_icc(), exif=exif)
    for ext in (".jpg", ".webp", ".png"):
        dst = tmp_path / f"out{ext}"
        compress(src, dst, ImageOptions())
        with Image.open(dst) as im:
            assert im.info.get("icc_profile") == _srgb_icc(), ext
            assert "TestCam" not in str(im.getexif().get(0x010F)), ext


def test_mismatched_icc_profile_dropped(tmp_path: Path):
    # A CMYK image is converted to RGB for JPEG; its CMYK profile no longer applies.
    src = tmp_path / "a.tif"
    fake_cmyk_icc = bytes(16) + b"CMYK" + bytes(108)
    Image.new("CMYK", (64, 64), (0, 255, 255, 0)).save(src, icc_profile=fake_cmyk_icc)
    dst = tmp_path / "a.jpg"
    compress(src, dst, ImageOptions())
    with Image.open(dst) as im:
        assert im.mode == "RGB" and "icc_profile" not in im.info
