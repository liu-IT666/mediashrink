from pathlib import Path

import pytest

from mediashrink import audio, ffmpeg, video
from tests.conftest import requires_ffmpeg


def test_video_args_h265_mp4():
    args = video.build_args(Path("in.mov"), Path("out.mp4"), video.VideoOptions(max_height=720))
    assert args[args.index("-c:v") + 1] == "libx265"
    assert args[args.index("-crf") + 1] == "28"
    assert "hvc1" in args
    assert "scale=-2:'min(720,ih)'" in args


def test_metadata_args():
    v = video.build_args(Path("in.mov"), Path("out.mp4"), video.VideoOptions())
    a = audio.build_args(Path("in.wav"), Path("out.m4a"), audio.AudioOptions())
    for args in (v, a):
        assert args[args.index("-map_metadata:g") + 1] == "-1" and "-map_metadata" not in args
    kept = audio.build_args(Path("in.wav"), Path("out.m4a"), audio.AudioOptions(strip_metadata=False))
    assert kept[kept.index("-map_metadata") + 1] == "0"


def test_audio_args_flac_has_no_bitrate():
    args = audio.build_args(Path("in.wav"), Path("out.flac"), audio.AudioOptions())
    assert "-b:a" not in args


@pytest.mark.parametrize(
    ("codec", "ext"), [("h264", ".webm"), ("h265", ".webm"), ("av1", ".mov"), ("vp9", ".mov"), ("h264", ".avi")]
)
def test_video_args_reject_bad_container(codec: str, ext: str):
    with pytest.raises(ValueError):
        video.build_args(Path("in.mov"), Path(f"out{ext}"), video.VideoOptions(codec=codec))


def _arg(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_preset_mapped_for_av1_and_vp9():
    av1 = video.build_args(Path("in.mov"), Path("out.mkv"), video.VideoOptions(codec="av1", preset="slow"))
    assert _arg(av1, "-preset") == "6"
    vp9 = video.build_args(Path("in.mov"), Path("out.webm"), video.VideoOptions(codec="vp9", preset="ultrafast"))
    assert _arg(vp9, "-cpu-used") == "5" and _arg(vp9, "-deadline") == "good" and _arg(vp9, "-b:v") == "0"
    assert _arg(vp9, "-c:a") == "libopus"


def test_unknown_preset_rejected():
    with pytest.raises(ValueError, match="preset"):
        video.build_args(Path("in.mov"), Path("out.mp4"), video.VideoOptions(preset="turbo"))


@requires_ffmpeg
def test_video_compress(sample_video: Path, tmp_path: Path):
    dst = tmp_path / "out.mp4"
    video.compress(sample_video, dst, video.VideoOptions(codec="h264", preset="ultrafast", max_height=240))
    streams = ffmpeg.probe(dst)["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    assert v["codec_name"] == "h264" and v["height"] == 240


@requires_ffmpeg
def test_audio_compress(sample_audio: Path, tmp_path: Path):
    dst = tmp_path / "out.m4a"
    audio.compress(sample_audio, dst, audio.AudioOptions(bitrate="64k"))
    assert dst.stat().st_size < sample_audio.stat().st_size
