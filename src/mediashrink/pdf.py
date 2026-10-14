"""PDF compression via pikepdf: recompress embedded images and streams."""

import io
from dataclasses import dataclass
from pathlib import Path

import pikepdf
from PIL import Image


@dataclass
class PdfOptions:
    image_quality: int = 70
    max_image_size: int | None = 2000  # longest edge, in px


def _shrink_images(pdf: pikepdf.Pdf, opts: PdfOptions) -> None:
    seen: set[tuple[int, int]] = set()
    for page in pdf.pages:
        for raw in page.get_images().values():
            if raw.objgen in seen:
                continue  # image shared across pages: already handled
            seen.add(raw.objgen)
            try:
                pdf_image = pikepdf.PdfImage(raw)
                im = pdf_image.as_pil_image()
            except Exception:
                continue  # unsupported colorspace / filter: leave untouched
            if raw.get("/SMask") is not None or im.mode not in ("RGB", "L"):
                continue  # transparency / exotic modes: re-encoding as JPEG would break them

            if opts.max_image_size:
                im.thumbnail((opts.max_image_size, opts.max_image_size), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=opts.image_quality, optimize=True)
            data = buf.getvalue()
            if len(data) >= len(raw.read_raw_bytes()):
                continue  # no gain

            raw.write(data, filter=pikepdf.Name.DCTDecode)
            raw.Width, raw.Height = im.width, im.height
            raw.ColorSpace = pikepdf.Name.DeviceRGB if im.mode == "RGB" else pikepdf.Name.DeviceGray
            raw.BitsPerComponent = 8
            for key in ("/DecodeParms", "/Decode"):
                if key in raw:
                    del raw[key]


def compress(src: Path, dst: Path, opts: PdfOptions) -> None:
    with pikepdf.open(src) as pdf:
        _shrink_images(pdf, opts)
        pdf.remove_unreferenced_resources()
        pdf.save(
            dst,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            recompress_flate=True,
        )
