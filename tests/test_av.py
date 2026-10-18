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


def test_vp9_row_multithreading():
    vp9 = video.build_args(Path("in.mov"), Path("out.webm"), video.VideoOptions(codec="vp9"))
    assert _arg(vp9, "-row-mt") == "1"


@pytest.mark.parametrize(
    ("value", "expected"), [("128k", 128_000), ("1.5M", 1_500_000), ("96000", 96_000), ("abc", None), ("0k", None)]
)
def test_parse_bitrate(value: str, expected: int | None):
    assert ffmpeg.parse_bitrate(value) == expected


AAC_64K = ffmpeg.AudioStream("aac", 64_781)  # what ffprobe reports for a "64k" AAC encode


@pytest.mark.parametrize(
    ("stream", "ext", "copied"),
    [
        (AAC_64K, ".mp4", True),
        (ffmpeg.AudioStream("aac", 192_000), ".mp4", False),  # bigger than --audio-bitrate: re-encode
        (ffmpeg.AudioStream("aac", None), ".mp4", False),  # unknown bit rate
        (AAC_64K, ".webm", False),  # webm cannot hold AAC
        (ffmpeg.AudioStream("opus", 48_000), ".webm", True),
        (ffmpeg.AudioStream("pcm_s16le", 64_000), ".mp4", False),
        (None, ".mp4", False),
    ],
)
def test_video_copies_small_audio(stream: ffmpeg.AudioStream | None, ext: str, copied: bool):
    codec = "vp9" if ext == ".webm" else "h264"
    args = video.build_args(Path("in.mov"), Path(f"out{ext}"), video.VideoOptions(codec=codec), stream)
    assert (_arg(args, "-c:a") == "copy") is copied
    assert ("-b:a" in args) is not copied


def test_audio_copies_small_audio():
    small_mp3 = ffmpeg.AudioStream("mp3", 96_000)
    args = audio.build_args(Path("in.mp3"), Path("out.mp3"), audio.AudioOptions(), small_mp3)
    assert _arg(args, "-c:a") == "copy" and "-b:a" not in args
    assert _arg(args, "-map_metadata:g") == "-1"  # metadata is still stripped
    # anything that changes the audio needs a re-encode
    for opts in (audio.AudioOptions(mono=True), audio.AudioOptions(sample_rate=22050), audio.AudioOptions("64k")):
        assert _arg(audio.build_args(Path("in.mp3"), Path("out.mp3"), opts, small_mp3), "-c:a") == "libmp3lame"
    # a different output codec, and flac (lossless) are always encoded
    assert _arg(audio.build_args(Path("in.mp3"), Path("out.m4a"), audio.AudioOptions(), small_mp3), "-c:a") == "aac"
    flac = ffmpeg.AudioStream("flac", 64_000)
    assert _arg(audio.build_args(Path("in.flac"), Path("out.flac"), audio.AudioOptions(), flac), "-c:a") == "flac"


@requires_ffmpeg
def test_small_audio_copied_end_to_end(sample_video: Path, tmp_path: Path):
    # sample_video has PCM audio: re-encoded to AAC. That AAC (128k) is then copied as-is by a 128k run.
    first = tmp_path / "first.mp4"
    video.compress(sample_video, first, video.VideoOptions(codec="h264", preset="ultrafast"))
    stream = ffmpeg.probe_audio(first)
    assert stream is not None and stream.codec == "aac" and stream.bit_rate is not None
    args = video.build_args(first, tmp_path / "second.mp4", video.VideoOptions(codec="h264"), stream)
    assert _arg(args, "-c:a") == "copy"
    video.compress(first, tmp_path / "second.mp4", video.VideoOptions(codec="h264", preset="ultrafast"))
    assert ffmpeg.probe_audio(tmp_path / "second.mp4") == stream  # bit-identical stream, same bit rate


@requires_ffmpeg
def test_audio_copy_m4a_to_adts(tmp_path: Path, sample_audio: Path):
    m4a = tmp_path / "a.m4a"
    audio.compress(sample_audio, m4a, audio.AudioOptions(bitrate="64k"))
    dst = tmp_path / "a.aac"
    stream = ffmpeg.probe_audio(m4a)
    assert _arg(audio.build_args(m4a, dst, audio.AudioOptions(), stream), "-c:a") == "copy"
    audio.compress(m4a, dst, audio.AudioOptions())  # ffmpeg accepts the copy into raw ADTS
    assert ffmpeg.probe_audio(dst).codec == "aac"


@requires_ffmpeg
def test_progress_reported(sample_video: Path, tmp_path: Path):
    seen: list[float] = []
    video.compress(
        sample_video, tmp_path / "out.mp4", video.VideoOptions(codec="h264", preset="ultrafast"), seen.append
    )
    assert seen and all(0 <= f <= 1 for f in seen) and seen[-1] > 0.9
