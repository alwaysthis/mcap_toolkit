"""Downsample (t, y) for display. CSV export should use full-resolution slices instead."""

from __future__ import annotations

import numpy as np


def downsample_xy(
    x: np.ndarray,
    y: np.ndarray,
    max_points: int = 8000,
) -> tuple[np.ndarray, np.ndarray]:
    n = int(x.size)
    if n <= max_points or max_points < 4:
        return x, y
    # Min/max buckets preserve peaks better than stride.
    bucket = n / float(max_points // 2)
    xs: list[float] = []
    ys: list[float] = []
    i = 0
    b = 0
    while i < n:
        j = min(n, int(round((b + 1) * bucket)))
        if j <= i:
            j = i + 1
        sl_y = y[i:j]
        sl_x = x[i:j]
        finite = np.isfinite(sl_y)
        if not np.any(finite):
            i = j
            b += 1
            continue
        yy = sl_y[finite]
        xx = sl_x[finite]
        imin = int(np.argmin(yy))
        imax = int(np.argmax(yy))
        if xx[imin] <= xx[imax]:
            xs.append(float(xx[imin]))
            ys.append(float(yy[imin]))
            if imax != imin:
                xs.append(float(xx[imax]))
                ys.append(float(yy[imax]))
        else:
            xs.append(float(xx[imax]))
            ys.append(float(yy[imax]))
            if imax != imin:
                xs.append(float(xx[imin]))
                ys.append(float(yy[imin]))
        i = j
        b += 1
    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)


def stairs_xy(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Hold-last step polyline so discrete 0/1/2 states are not linearly interpolated."""
    if x.size == 0:
        return x, y
    xs: list[float] = []
    ys: list[float] = []
    for i in range(int(x.size)):
        if i > 0:
            xs.append(float(x[i]))
            ys.append(float(y[i - 1]))
        xs.append(float(x[i]))
        ys.append(float(y[i]))
    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)
