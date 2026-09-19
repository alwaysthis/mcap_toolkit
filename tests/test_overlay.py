"""ROI overlay must copy the canvas; source pixels stay unchanged."""

from __future__ import annotations

import numpy as np

from mcap_toolkit.image.overlay import render_rois_on_image


def test_overlay_does_not_mutate_source() -> None:
    src = np.zeros((40, 50, 3), dtype=np.uint8)
    src[:] = (10, 20, 30)
    orig = src.copy()
    rois = [{"x": 5, "y": 6, "width": 12, "height": 10, "shape": "rect"}]
    out = render_rois_on_image(src, rois)
    assert np.array_equal(src, orig)
    assert out is not src
    assert not np.array_equal(out, orig)


def test_overlay_gray_source_unchanged() -> None:
    gray = np.arange(100, dtype=np.uint8).reshape(10, 10)
    orig = gray.copy()
    out = render_rois_on_image(
        gray, [{"x": 1, "y": 1, "width": 4, "height": 4, "shape": "ellipse"}]
    )
    assert np.array_equal(gray, orig)
    assert out.ndim == 3
