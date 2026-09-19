"""OpenCV fallback can write a tiny MP4 without ffmpeg.exe."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mcap_toolkit.export.video_export import write_video_opencv


def test_opencv_writes_mp4(tmp_path: Path) -> None:
    frames = [
        np.full((48, 64, 3), 40, dtype=np.uint8),
        np.full((48, 64, 3), 80, dtype=np.uint8),
        np.full((48, 64, 3), 120, dtype=np.uint8),
    ]
    out = tmp_path / "clip.mp4"
    write_video_opencv(out, iter(frames), fps=8.0)
    assert out.is_file()
    assert out.stat().st_size > 0
