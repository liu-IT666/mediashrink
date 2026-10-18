import subprocess
from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from mediashrink import ffmpeg
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
    # An invalid bitrate makes ffmpeg fail after it has already created the output file.
    args = ["video", str(sample_video), "-c", "h264", "--preset", "ultrafast", "--audio-bitrate", "abc"]
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


def test_batch_output_collision(tmp_path: Path):
    # a.png and a.jpg both default to a.min.jpg: the second must not overwrite the first, even with -y.
    Image.effect_noise((400, 300), 64).convert("RGB").save(tmp_path / "a.png")
    _low_quality_jpeg(tmp_path / "a.jpg")
    result = runner.invoke(app, ["image", str(tmp_path / "a.png"), str(tmp_path / "a.jpg"), "-f", "jpg", "-y"])
    assert result.exit_code == 1
    assert "same output as a.png" in result.output
    assert (tmp_path / "a.min.jpg").exists()


def test_collision_ignores_input_that_wrote_nothing(tmp_path: Path):
    bad = tmp_path / "a.png"
    bad.write_text("not an image")
    Image.effect_noise((400, 300), 64).convert("RGB").save(tmp_path / "a.bmp")
    result = runner.invoke(app, ["image", str(bad), str(tmp_path / "a.bmp"), "-f", "jpg"])
    assert result.exit_code == 1  # a.png failed...
    assert (tmp_path / "a.min.jpg").exists()  # ...so a.bmp may still write a.min.jpg


def test_video_rejects_codec_container_mismatch_early(tmp_path: Path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"not even a video")  # never reaches ffmpeg
    result = runner.invoke(app, ["video", str(src), "-c", "h265", "-f", "webm"])
    assert result.exit_code == 1
    assert "h265 cannot be stored in .webm" in result.output


def test_auto_animated_gif_to_webp(tmp_path: Path):
    src = tmp_path / "a.gif"
    frames = [Image.effect_noise((200, 150), 40 + 10 * i).convert("P") for i in range(4)]
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=80, loop=0)
    result = runner.invoke(app, ["auto", str(src), "--keep-larger"])
    assert result.exit_code == 0, result.output
    with Image.open(tmp_path / "a.min.webp") as im:
        assert im.n_frames == 4


def test_batch_into_missing_output_dir(tmp_path: Path):
    srcs = []
    for name in ("a", "b"):
        Image.effect_noise((300, 200), 64).convert("RGB").save(tmp_path / f"{name}.png")
        srcs.append(str(tmp_path / f"{name}.png"))
    result = runner.invoke(app, ["image", *srcs, "-f", "webp", "-o", f"{tmp_path / 'out'}/"])
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a.webp", "b.webp"]


def _tagged_video(path: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=128x96:rate=10:duration=0.5",
         "-f", "lavfi", "-i", "sine=duration=0.5", "-c:v", "mpeg4", "-c:a", "aac", "-shortest",
         "-metadata", "location=+39.9000+116.4000/", "-metadata:s:a:0", "language=jpn", str(path)],
        check=True,
    )  # fmt: skip
    return path


@requires_ffmpeg
def test_video_metadata_stripped_by_default(tmp_path: Path):
    src = _tagged_video(tmp_path / "a.mp4")
    base = ["video", str(src), "-c", "h264", "--preset", "ultrafast", "--keep-larger", "-y"]
    assert runner.invoke(app, base).exit_code == 0
    info = ffmpeg.probe(tmp_path / "a.min.mp4")
    assert "location" not in info["format"].get("tags", {})  # GPS gone
    audio_tags = next(s for s in info["streams"] if s["codec_type"] == "audio")["tags"]
    assert audio_tags["language"] == "jpn"  # per-stream tags players rely on are kept

    assert runner.invoke(app, [*base, "--keep-metadata"]).exit_code == 0
    assert "location" in ffmpeg.probe(tmp_path / "a.min.mp4")["format"]["tags"]
