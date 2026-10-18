"""Image conversion / compression via Pillow."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

# output extension -> Pillow format name
IMAGE_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".avif": "AVIF",
}


@dataclass
class ImageOptions:
    quality: int = 80
    max_size: int | None = None  # longest edge, in px
    strip_metadata: bool = True  # EXIF only; the ICC color profile is always kept


# ICC header bytes 16..20 name the profile's color space; it is only valid for matching pixel data
_ICC_SPACES = {"RGB": b"RGB ", "RGBA": b"RGB ", "P": b"RGB ", "PA": b"RGB ", "L": b"GRAY", "LA": b"GRAY"}


def _icc_profile(im: Image.Image) -> bytes | None:
    icc = im.info.get("icc_profile")
    if icc and icc[16:20] == _ICC_SPACES.get(im.mode):
        return icc
    return None  # none, or no longer matches after e.g. CMYK -> RGB


def compress(src: Path, dst: Path, opts: ImageOptions) -> None:
    fmt = IMAGE_FORMATS.get(dst.suffix.lower())
    if fmt is None:
        raise ValueError(f"Unsupported image format {dst.suffix!r}; choose from {', '.join(IMAGE_FORMATS)}")

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # bake in rotation before metadata is dropped
        if opts.max_size:
            im.thumbnail((opts.max_size, opts.max_size), Image.Resampling.LANCZOS)
        if fmt == "JPEG" and im.mode not in ("RGB", "L"):
            im = im.convert("RGB")

        save_kwargs: dict = {}
        if fmt == "PNG":
            save_kwargs["optimize"] = True
        else:
            save_kwargs["quality"] = opts.quality
        if fmt == "JPEG":
            save_kwargs.update(optimize=True, progressive=True)
        if icc := _icc_profile(im):
            save_kwargs["icc_profile"] = icc  # dropping it shifts colors (e.g. Display P3 photos)
        if not opts.strip_metadata and "exif" in im.info:
            save_kwargs["exif"] = im.info["exif"]
        im.save(dst, fmt, **save_kwargs)
