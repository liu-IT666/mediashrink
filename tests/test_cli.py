from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from mediashrink.cli import app

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
