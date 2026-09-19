"""ROI overlay colors (1-based), duplicated from clc_mbe so this toolkit stays independent."""

from __future__ import annotations

# Order: green, red, cyan, yellow, magenta, orange.
ROI_COLORS_RGB: tuple[tuple[int, int, int], ...] = (
    (0, 255, 0),
    (255, 60, 60),
    (0, 200, 255),
    (255, 255, 0),
    (255, 0, 255),
    (255, 128, 0),
)

ROI_COLORS_BGR: tuple[tuple[int, int, int], ...] = tuple((b, g, r) for r, g, b in ROI_COLORS_RGB)


def _clamp_index(index: int) -> int:
    n = len(ROI_COLORS_RGB)
    if n <= 0:
        return 1
    return ((int(index) - 1) % n) + 1


def roi_color_bgr(index: int) -> tuple[int, int, int]:
    i = _clamp_index(index)
    return ROI_COLORS_BGR[i - 1]


def roi_color_hex(index: int) -> str:
    i = _clamp_index(index)
    r, g, b = ROI_COLORS_RGB[i - 1]
    return f"#{r:02x}{g:02x}{b:02x}"
