import zlib
from pathlib import Path

import pikepdf
from PIL import Image

from mediashrink.pdf import PdfOptions, compress


def test_pdf_with_large_image_shrinks(tmp_path: Path):
    src = tmp_path / "a.pdf"
    Image.effect_noise((2400, 1800), 32).convert("RGB").save(src, "PDF", resolution=300, quality=95)
    dst = tmp_path / "a.min.pdf"
    compress(src, dst, PdfOptions(image_quality=60, max_image_size=1200))
    assert dst.stat().st_size < src.stat().st_size


def _image_stream(pdf: pikepdf.Pdf, im: Image.Image, **extra) -> pikepdf.Stream:
    """Flate-compressed image XObject (what most PDF producers emit for lossless images)."""
    if im.mode == "P":
        palette = bytes(im.getpalette()[: 3 * 256])
        cs = pikepdf.Array([pikepdf.Name.Indexed, pikepdf.Name.DeviceRGB, 255, pikepdf.String(palette)])
    else:
        cs = pikepdf.Name.DeviceRGB if im.mode == "RGB" else pikepdf.Name.DeviceGray
    return pikepdf.Stream(
        pdf,
        zlib.compress(im.tobytes()),
        Type=pikepdf.Name.XObject,
        Subtype=pikepdf.Name.Image,
        Width=im.width,
        Height=im.height,
        ColorSpace=cs,
        BitsPerComponent=8,
        Filter=pikepdf.Name.FlateDecode,
        **extra,
    )


def _noise(mode: str = "RGB") -> Image.Image:
    im = Image.effect_noise((800, 600), 40).convert("RGB")
    return im.quantize(256) if mode == "P" else im.convert(mode)


def _pdf_with(tmp_path: Path, make_xobjects, in_form: bool = False) -> Path:
    """One page drawing the given images, either directly or from inside a Form XObject."""
    pdf = pikepdf.new()
    images = make_xobjects(pdf)
    draw = b" ".join(b"q 100 0 0 100 0 0 cm /%s Do Q" % name.encode() for name in images)
    resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary({f"/{k}": v for k, v in images.items()}))
    if in_form:
        form = pikepdf.Stream(pdf, draw, Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Form)
        form.BBox, form.Resources = pikepdf.Array([0, 0, 612, 792]), resources
        resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fm0=form))
        draw = b"q /Fm0 Do Q"
    page = pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=pikepdf.Array([0, 0, 612, 792])))
    pdf.pages.append(page)
    pdf.pages[0].Resources = resources
    pdf.pages[0].Contents = pdf.make_stream(draw)
    src = tmp_path / "in.pdf"
    pdf.save(src)
    return src


def _out_images(path: Path) -> list[dict]:
    with pikepdf.open(path) as pdf:
        return [
            {"w": int(o.Width), "filter": o.get("/Filter"), "smask": "/SMask" in o}
            for o in pdf.objects
            if isinstance(o, pikepdf.Stream) and o.get("/Subtype") == pikepdf.Name.Image
        ]


def test_image_inside_form_xobject_shrinks(tmp_path: Path):
    src = _pdf_with(tmp_path, lambda pdf: {"Im0": _image_stream(pdf, _noise())}, in_form=True)
    dst = tmp_path / "out.pdf"
    compress(src, dst, PdfOptions(max_image_size=400))
    assert _out_images(dst) == [{"w": 400, "filter": pikepdf.Name.DCTDecode, "smask": False}]


def test_indexed_image_recompressed(tmp_path: Path):
    src = _pdf_with(tmp_path, lambda pdf: {"Im0": _image_stream(pdf, _noise("P"))})
    dst = tmp_path / "out.pdf"
    compress(src, dst, PdfOptions(max_image_size=400))
    assert _out_images(dst) == [{"w": 400, "filter": pikepdf.Name.DCTDecode, "smask": False}]
    with pikepdf.open(dst) as pdf:
        img = next(o for o in pdf.objects if isinstance(o, pikepdf.Stream) and o.get("/Subtype") == "/Image")
        assert img.ColorSpace == pikepdf.Name.DeviceRGB


def test_masked_images_left_alone(tmp_path: Path):
    def make(pdf):
        smask = _image_stream(pdf, _noise("L"))
        return {
            "Im0": _image_stream(pdf, _noise(), SMask=smask),  # soft mask (alpha)
            "Im1": _image_stream(pdf, _noise(), Mask=pikepdf.Array([0, 10, 0, 10, 0, 10])),  # color-key mask
        }

    src = _pdf_with(tmp_path, make)
    dst = tmp_path / "out.pdf"
    compress(src, dst, PdfOptions(max_image_size=400))
    images = _out_images(dst)
    assert len(images) == 3  # two images + the soft mask itself
    assert all(i["w"] == 800 and i["filter"] == pikepdf.Name.FlateDecode for i in images)
