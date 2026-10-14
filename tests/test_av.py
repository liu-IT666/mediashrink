from pathlib import Path

from mediashrink import audio, ffmpeg, video
from tests.conftest import requires_ffmpeg


def test_video_args_h265_mp4():
    args = video.build_args(Path("in.mov"), Path("out.mp4"), video.VideoOptions(max_height=720))
    assert args[args.index("-c:v") + 1] == "libx265"
    assert args[args.index("-crf") + 1] == "28"
    assert "hvc1" in args
    assert "scale=-2:'min(720,ih)'" in args


def test_audio_args_flac_has_no_bitrate():
    args = audio.build_args(Path("in.wav"), Path("out.flac"), audio.AudioOptions())
    assert "-b:a" not in args


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
