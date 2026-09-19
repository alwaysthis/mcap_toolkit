"""Decode CompressedImage JPEG/PNG bytes to numpy arrays. No Qt."""

from __future__ import annotations

import io

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

from PIL import Image


def decode_compressed_image(data: bytes, fmt: str = "") -> np.ndarray:
    """Return uint8 array: HxW (gray) or HxWx3 BGR (color), matching OpenCV convention."""
    if not data:
        raise ValueError("empty image bytes")
    fmt_l = (fmt or "").lower()

    if cv2 is not None:
        buf = np.frombuffer(data, dtype=np.uint8)
        flags = cv2.IMREAD_UNCHANGED
        if "jpeg" in fmt_l or "jpg" in fmt_l:
            flags = cv2.IMREAD_UNCHANGED
        decoded = cv2.imdecode(buf, flags)
        if decoded is not None and decoded.size > 0:
            if decoded.ndim == 3 and decoded.shape[2] == 4:
                decoded = cv2.cvtColor(decoded, cv2.COLOR_BGRA2BGR)
            return decoded

    with Image.open(io.BytesIO(data)) as pil:
        if "png" in fmt_l or pil.format == "PNG":
            pil.load()
        if pil.mode in {"I;16", "I"}:
            arr = np.array(pil, dtype=np.uint16)
            return np.clip(arr / 256.0, 0, 255).astype(np.uint8)
        if pil.mode == "L":
            return np.array(pil, dtype=np.uint8)
        rgb = np.array(pil.convert("RGB"), dtype=np.uint8)
        # PIL RGB → BGR for overlay/OpenCV
        return rgb[:, :, ::-1].copy()
