"""Image conversion / compression via Pillow."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence
from pillow_heif import register_heif_opener

register_heif_opener()  # lets Image.open read HEIC/HEIF (e.g. iPhone photos)

# output extension -> Pillow format name
IMAGE_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".avif": "AVIF",
}
# output formats that can hold all frames of an animated input (GIF, animated WebP, ...)
ANIMATED_FORMATS = {"PNG", "WEBP", "AVIF"}
# input formats whose extra frames are an animation; for others (MPO JPEGs with an embedded
# preview/depth map, multi-page TIFF, HEIF) the first image is the picture
_ANIMATION_INPUTS = {"GIF", "PNG", "WEBP", "AVIF"}


def default_suffix(src: Path) -> str:
    """Output extension when none is given: keep a supported one, else .webp for GIF (may be animated), else .jpg."""
    ext = src.suffix.lower()
    if ext in IMAGE_FORMATS:
        return ext
    return ".webp" if ext == ".gif" else ".jpg"


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


def _resize(im: Image.Image, opts: ImageOptions) -> Image.Image:
    if opts.max_size:
        im.thumbnail((opts.max_size, opts.max_size), Image.Resampling.LANCZOS)
    return im


def compress(src: Path, dst: Path, opts: ImageOptions) -> None:
    fmt = IMAGE_FORMATS.get(dst.suffix.lower())
    if fmt is None:
        raise ValueError(f"Unsupported image format {dst.suffix!r}; choose from {', '.join(IMAGE_FORMATS)}")

    with Image.open(src) as im:
        save_kwargs: dict = {}
        if im.format in _ANIMATION_INPUTS and getattr(im, "is_animated", False):
            if fmt not in ANIMATED_FORMATS:
                raise ValueError(f"{src.name} is animated; {fmt} would keep only the first frame (use webp/png/avif)")
            frames, durations = [], []
            for frame in ImageSequence.Iterator(im):
                frame.load()  # some readers (WebP) only fill info["duration"] on load
                durations.append(frame.info.get("duration", 100))
                frames.append(_resize(frame.convert("RGBA"), opts))  # frames may mix P/RGB/RGBA modes
            im = frames[0]
            save_kwargs.update(save_all=True, append_images=frames[1:], duration=durations, loop=im.info.get("loop", 0))
        else:
            im = _resize(ImageOps.exif_transpose(im), opts)  # bake in rotation before metadata is dropped
            if fmt == "JPEG" and im.mode not in ("RGB", "L"):
                im = im.convert("RGB")

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
