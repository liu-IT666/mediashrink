import shutil
import subprocess
from pathlib import Path

import pytest

requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    dst = tmp_path / "sample.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x480:rate=25:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "mpeg4",
            "-q:v",
            "2",
            "-c:a",
            "pcm_s16le",
            "-shortest",
            str(dst),
        ],
        check=True,
    )
    return dst


@pytest.fixture
def sample_audio(tmp_path: Path) -> Path:
    dst = tmp_path / "sample.wav"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(dst)],
        check=True,
    )
    return dst
