from pathlib import Path

import pytest
from PIL import Image, ImageCms

from mediashrink.image import ImageOptions, compress, default_suffix


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


def test_heic_input(tmp_path: Path):
    src = tmp_path / "a.heic"
    Image.effect_noise((640, 480), 64).convert("RGB").save(src, quality=95)  # pillow-heif registers the encoder too
    dst = tmp_path / "a.jpg"
    compress(src, dst, ImageOptions(max_size=320))
    with Image.open(dst) as im:
        assert im.format == "JPEG" and im.size == (320, 240)


def _animated_gif(path: Path, n: int = 3) -> Path:
    frames = [Image.new("RGB", (60, 40), c).convert("P") for c in ("red", "green", "blue")[:n]]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[100, 200, 300][:n], loop=0)
    return path


@pytest.mark.parametrize("ext", [".webp", ".png"])
def test_animated_frames_and_timing_kept(tmp_path: Path, ext: str):
    dst = tmp_path / f"a{ext}"
    compress(_animated_gif(tmp_path / "a.gif"), dst, ImageOptions(max_size=30))
    with Image.open(dst) as im:
        assert im.n_frames == 3 and im.size == (30, 20)
        durations = []
        for i in range(3):
            im.seek(i)
            im.load()  # the WebP reader fills info["duration"] on load
            durations.append(im.info["duration"])
        assert durations == [100, 200, 300]


def test_animated_webp_input_keeps_timing(tmp_path: Path):
    src = tmp_path / "a.webp"
    frames = [Image.new("RGB", (60, 40), c) for c in ("red", "green", "blue")]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=0)
    dst = tmp_path / "out.webp"
    compress(src, dst, ImageOptions())
    with Image.open(dst) as im:
        durations = []
        for i in range(im.n_frames):
            im.seek(i)
            im.load()
            durations.append(im.info["duration"])
    assert durations == [100, 200, 300]


def test_animated_to_jpeg_refused(tmp_path: Path):
    with pytest.raises(ValueError, match="animated"):
        compress(_animated_gif(tmp_path / "a.gif"), tmp_path / "a.jpg", ImageOptions())


def test_multi_image_jpeg_is_not_an_animation(tmp_path: Path):
    # MPO: a JPEG carrying extra images (camera preview, depth map). Only the primary one is the photo.
    src = tmp_path / "a.jpg"
    Image.new("RGB", (64, 48), "red").save(src, "MPO", save_all=True, append_images=[Image.new("RGB", (32, 24))])
    dst = tmp_path / "out.jpg"
    compress(src, dst, ImageOptions())
    with Image.open(dst) as im:
        assert im.size == (64, 48)


def test_default_suffix():
    assert default_suffix(Path("a.PNG")) == ".png"
    assert default_suffix(Path("a.gif")) == ".webp"
    assert default_suffix(Path("a.heic")) == ".jpg"
