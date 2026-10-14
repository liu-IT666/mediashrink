from pathlib import Path

from PIL import Image

from mediashrink.pdf import PdfOptions, compress


def test_pdf_with_large_image_shrinks(tmp_path: Path):
    src = tmp_path / "a.pdf"
    Image.effect_noise((2400, 1800), 32).convert("RGB").save(src, "PDF", resolution=300, quality=95)
    dst = tmp_path / "a.min.pdf"
    compress(src, dst, PdfOptions(image_quality=60, max_image_size=1200))
    assert dst.stat().st_size < src.stat().st_size
