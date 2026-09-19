"""Write MP4. Prefer ffmpeg on PATH; otherwise OpenCV (already a project dependency)."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

FFMPEG_HINT = (
    "ffmpeg was not found, and OpenCV could not write the video.\n"
    "Windows (optional): winget install ffmpeg\n"
    "Or download from https://ffmpeg.org/download.html and add it to PATH."
)


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _to_rgb(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return np.stack([frame, frame, frame], axis=-1)
    if frame.ndim == 3 and frame.shape[2] == 3:
        return frame[:, :, ::-1].copy()
    if frame.ndim == 3 and frame.shape[2] >= 3:
        bgr = frame[:, :, :3]
        return bgr[:, :, ::-1].copy()
    raise ValueError(f"unsupported frame shape: {frame.shape}")


def _to_bgr(frame: np.ndarray) -> np.ndarray:
    arr = np.ascontiguousarray(frame)
    if arr.ndim == 2:
        return np.stack([arr, arr, arr], axis=-1)
    if arr.ndim == 3 and arr.shape[2] == 3:
        return arr
    if arr.ndim == 3 and arr.shape[2] >= 3:
        return np.ascontiguousarray(arr[:, :, :3])
    raise ValueError(f"unsupported frame shape: {arr.shape}")


def _even_bgr(frame: np.ndarray) -> np.ndarray:
    bgr = _to_bgr(frame)
    h, w = bgr.shape[:2]
    nh, nw = h - (h % 2), w - (w % 2)
    if nh < 2 or nw < 2:
        raise ValueError("frame too small to encode")
    if nh != h or nw != w:
        bgr = bgr[:nh, :nw]
    return np.ascontiguousarray(bgr, dtype=np.uint8)


def write_video(
    path: str | Path,
    frames: Iterator[np.ndarray],
    *,
    fps: float = 10.0,
    progress: Callable[[int], None] | None = None,
) -> None:
    if find_ffmpeg():
        write_video_ffmpeg(path, frames, fps=fps, progress=progress)
        return
    write_video_opencv(path, frames, fps=fps, progress=progress)


def write_video_ffmpeg(
    path: str | Path,
    frames: Iterator[np.ndarray],
    *,
    fps: float = 10.0,
    ffmpeg_bin: str | None = None,
    progress: Callable[[int], None] | None = None,
) -> None:
    bin_path = ffmpeg_bin or find_ffmpeg()
    if not bin_path:
        raise FileNotFoundError(FFMPEG_HINT)

    first = next(frames, None)
    if first is None:
        raise ValueError("no frames to export")
    rgb0 = _to_rgb(np.ascontiguousarray(first))
    h, w = rgb0.shape[:2]
    fps = max(1.0, float(fps))
    cmd = [
        bin_path,
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        f"{fps:.4f}",
        "-i",
        "-",
        "-an",
        "-vcodec",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    assert proc.stdin is not None
    count = 0
    try:
        proc.stdin.write(np.ascontiguousarray(rgb0).tobytes())
        count = 1
        if progress:
            progress(count)
        for frame in frames:
            rgb = _to_rgb(np.ascontiguousarray(frame))
            if rgb.shape[0] != h or rgb.shape[1] != w:
                from PIL import Image

                rgb = np.array(Image.fromarray(rgb).resize((w, h)), dtype=np.uint8)
            proc.stdin.write(np.ascontiguousarray(rgb).tobytes())
            count += 1
            if progress:
                progress(count)
    finally:
        proc.stdin.close()
        _err = proc.stderr.read() if proc.stderr else b""
        rc = proc.wait()
    if rc != 0:
        msg = _err.decode("utf-8", errors="replace")[-800:]
        raise RuntimeError(f"ffmpeg failed ({rc}): {msg}")


def write_video_opencv(
    path: str | Path,
    frames: Iterator[np.ndarray],
    *,
    fps: float = 10.0,
    progress: Callable[[int], None] | None = None,
) -> None:
    if cv2 is None:
        raise FileNotFoundError(FFMPEG_HINT)

    first = next(frames, None)
    if first is None:
        raise ValueError("no frames to export")
    bgr0 = _even_bgr(first)
    h, w = bgr0.shape[:2]
    fps = max(1.0, float(fps))
    out = Path(path)
    writer = None
    last_error = ""
    for fourcc_name in ("mp4v", "avc1", "XVID"):
        fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
        candidate = cv2.VideoWriter(str(out), fourcc, fps, (w, h))
        if candidate.isOpened():
            writer = candidate
            break
        candidate.release()
        last_error = fourcc_name
    if writer is None:
        raise RuntimeError(f"OpenCV could not create the video file (tried {last_error}). {FFMPEG_HINT}")

    count = 0
    try:
        writer.write(bgr0)
        count = 1
        if progress:
            progress(count)
        for frame in frames:
            bgr = _even_bgr(frame)
            if bgr.shape[0] != h or bgr.shape[1] != w:
                bgr = cv2.resize(bgr, (w, h), interpolation=cv2.INTER_AREA)
            writer.write(bgr)
            count += 1
            if progress:
                progress(count)
    finally:
        writer.release()
    if count < 1:
        raise ValueError("no frames to export")
