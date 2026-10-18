from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from mediashrink.cli import app
from tests.conftest import requires_ffmpeg

runner = CliRunner()


def test_image_cli(tmp_path: Path):
    src = tmp_path / "a.png"
    Image.effect_noise((400, 300), 64).convert("RGB").save(src)
    result = runner.invoke(app, ["image", str(src), "-f", "webp"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "a.min.webp").exists()


def test_auto_rejects_unknown(tmp_path: Path):
    src = tmp_path / "a.xyz"
    src.write_text("x")
    result = runner.invoke(app, ["auto", str(src)])
    assert result.exit_code == 1


def test_bad_pdf_does_not_abort_batch(tmp_path: Path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 garbage")
    good = tmp_path / "good.pdf"
    Image.effect_noise((2400, 1800), 32).convert("RGB").save(good, "PDF", resolution=300, quality=95)
    result = runner.invoke(app, ["pdf", str(bad), str(good)])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), result.exception  # reported, not a traceback
    assert "bad.pdf" in result.output
    assert (tmp_path / "good.min.pdf").exists()
    assert not (tmp_path / "bad.min.pdf").exists()


def _low_quality_jpeg(path: Path) -> Path:
    Image.effect_noise((400, 300), 64).convert("RGB").save(path, quality=30)
    return path


def test_larger_output_discarded(tmp_path: Path):
    src = _low_quality_jpeg(tmp_path / "a.jpg")
    result = runner.invoke(app, ["image", str(src), "-q", "95"])
    assert result.exit_code == 0, result.output
    assert "discarded" in result.output
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.jpg"]


def test_keep_larger(tmp_path: Path):
    src = _low_quality_jpeg(tmp_path / "a.jpg")
    result = runner.invoke(app, ["image", str(src), "-q", "95", "--keep-larger"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "a.min.jpg").stat().st_size > src.stat().st_size


@requires_ffmpeg
def test_failed_encode_leaves_no_output(sample_video: Path):
    # h265 cannot go into webm: ffmpeg fails after it has already created the output file.
    args = ["video", str(sample_video), "-c", "h265", "-f", "webm"]
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert sorted(p.name for p in sample_video.parent.iterdir()) == ["sample.mov"]
    # ...so a retry is not blocked by a stale "Output already exists".
    result = runner.invoke(app, args)
    assert "already exists" not in result.output


@requires_ffmpeg
def test_info_reports_probe_error(tmp_path: Path):
    src = tmp_path / "a.txt"
    src.write_text("not media")
    result = runner.invoke(app, ["info", str(src)])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), result.exception
