"""Draw ROI outlines on a copy of the image. Never mutates the source array."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

from mcap_toolkit.image.colors import roi_color_bgr


def _normalize_shape(roi: dict[str, Any]) -> str:
    raw = roi.get("shape", "ellipse")
    return "rect" if str(raw).strip().lower() == "rect" else "ellipse"


def _to_bgr_uint8(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        raise ValueError("empty image")
    out = image
    if out.dtype != np.uint8:
        if np.issubdtype(out.dtype, np.floating):
            out = np.clip(out, 0, 1) * 255.0
        out = np.clip(out, 0, 255).astype(np.uint8)
    if out.ndim == 2:
        if cv2 is not None:
            return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        return np.stack([out, out, out], axis=-1)
    if out.ndim == 3 and out.shape[2] >= 3:
        if out.shape[2] == 3:
            return out.copy()
        return out[:, :, :3].copy()
    raise ValueError(f"unsupported image shape: {out.shape}")


def render_rois_on_image(image: np.ndarray, rois: Sequence[dict[str, Any]] | None) -> np.ndarray:
    """Return BGR uint8 image with ROI outlines and 1-based index labels."""
    canvas = _to_bgr_uint8(image)
    if cv2 is None:
        return canvas
    h, w = canvas.shape[:2]
    for idx, roi in enumerate(rois or [], start=1):
        if not isinstance(roi, dict):
            continue
        try:
            x = int(roi.get("x", 0))
            y = int(roi.get("y", 0))
            rw = int(roi.get("width", 0))
            rh = int(roi.get("height", 0))
        except Exception:
            continue
        if rw <= 0 or rh <= 0:
            continue
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        rw = min(rw, w - x)
        rh = min(rh, h - y)
        if rw <= 0 or rh <= 0:
            continue
        color = roi_color_bgr(idx)
        x2 = x + rw - 1
        y2 = y + rh - 1
        if _normalize_shape(roi) == "rect":
            cv2.rectangle(canvas, (x, y), (x2, y2), color, 2, lineType=cv2.LINE_AA)
        else:
            center = (x + (rw - 1) / 2.0, y + (rh - 1) / 2.0)
            axes = (max(1, rw) / 2.0, max(1, rh) / 2.0)
            cv2.ellipse(
                canvas,
                (int(round(center[0])), int(round(center[1]))),
                (int(round(axes[0])), int(round(axes[1]))),
                0,
                0,
                360,
                color,
                2,
                lineType=cv2.LINE_AA,
            )
        cv2.putText(
            canvas,
            str(idx),
            (x + 4, y + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            lineType=cv2.LINE_AA,
        )
    return canvas
