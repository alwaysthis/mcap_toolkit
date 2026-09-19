"""Time-axis helpers. Qt-free.

Relative time (default): seconds from the first message, axis starts at 0.
Absolute time: local wall-clock hour:minute:second.

Plot X is always seconds-from-t0. Absolute mode only changes tick / playhead labels.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum

import numpy as np


class TimeMode(str, Enum):
    RELATIVE = "relative"  # seconds from 0
    ABSOLUTE = "absolute"  # local clock HH:MM:SS


def xlabel_for_mode(mode: TimeMode | str) -> str:
    value = mode.value if isinstance(mode, TimeMode) else str(mode)
    if value == TimeMode.ABSOLUTE.value:
        return "Time"
    return "Time (sec.)"


def is_clock_mode(mode: TimeMode | str) -> bool:
    value = mode.value if isinstance(mode, TimeMode) else str(mode)
    return value == TimeMode.ABSOLUTE.value


def ns_to_seconds_from_start(t_ns: np.ndarray | int | float, t0_ns: int) -> np.ndarray | float:
    """Relative seconds. Subtract in integer ns first so epoch timestamps don't lose precision."""
    t0 = int(t0_ns)
    arr = np.asarray(t_ns, dtype=np.int64)
    out = (arr - t0).astype(np.float64) / 1e9
    if out.ndim == 0:
        return float(out)
    return out


def ns_to_epoch_s(t_ns: np.ndarray | int | float) -> np.ndarray | float:
    arr = np.asarray(t_ns, dtype=np.float64)
    return arr / 1e9


def x_values(t_ns: np.ndarray, t0_ns: int, mode: TimeMode | str | None = None) -> np.ndarray:
    """Plot X is always seconds from the first message. Mode only affects tick labels."""
    return np.asarray(ns_to_seconds_from_start(t_ns, t0_ns), dtype=np.float64)


def rel_seconds_to_ns(t0_ns: int, rel_s: float) -> int:
    """Map plot X (seconds from t0) back to log_time nanoseconds without float64 epoch loss."""
    return int(t0_ns) + int(round(float(rel_s) * 1e9))


def playhead_ns_from_ratio(t0_ns: int, t1_ns: int, ratio: float) -> int:
    """Map a 0–1 seek ratio onto [t0, t1] without promoting epoch ns to float64."""
    t0 = int(t0_ns)
    span = max(0, int(t1_ns) - t0)
    r = max(0.0, min(1.0, float(ratio)))
    return t0 + int(round(r * span))


def ratio_from_playhead(t0_ns: int, t1_ns: int, t_ns: int) -> float:
    t0 = int(t0_ns)
    span = int(t1_ns) - t0
    if span <= 0:
        return 0.0
    t = min(max(int(t_ns), t0), t0 + span)
    return (t - t0) / span


_NICE_STEPS_S = (
    1e-3,
    2e-3,
    5e-3,
    1e-2,
    2e-2,
    5e-2,
    0.1,
    0.2,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    15.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
    900.0,
    1800.0,
    3600.0,
    7200.0,
    10800.0,
    21600.0,
    43200.0,
    86400.0,
)


def nice_clock_step(span_s: float, target_ticks: int = 6) -> float:
    raw = abs(float(span_s)) / max(int(target_ticks), 1)
    if not math.isfinite(raw) or raw <= 0:
        return 1.0
    for step in _NICE_STEPS_S:
        if step >= raw:
            return float(step)
    return float(_NICE_STEPS_S[-1])


def _utc_offset_seconds() -> float:
    off = datetime.now().astimezone().utcoffset()
    return off.total_seconds() if off is not None else 0.0


def clock_tick_positions(t0_ns: int, min_rel: float, max_rel: float, step: float) -> list[float]:
    """Relative-second tick locations aligned to local wall-clock multiples of `step`."""
    if step <= 0 or not math.isfinite(min_rel) or not math.isfinite(max_rel):
        return []
    lo, hi = (min_rel, max_rel) if min_rel <= max_rel else (max_rel, min_rel)
    t0_s = int(t0_ns) / 1e9
    offset = _utc_offset_seconds()
    local_lo = t0_s + lo + offset
    first = math.ceil(local_lo / step - 1e-12) * step
    out: list[float] = []
    local = first
    local_hi = t0_s + hi + offset
    n = 0
    while local <= local_hi + 1e-9 and n < 400:
        rel = local - offset - t0_s
        if lo - 1e-9 <= rel <= hi + 1e-9:
            out.append(rel)
        local += step
        n += 1
    return out


def format_clock_hms(t_ns: int, *, millis: bool = False) -> str:
    sec = int(t_ns) / 1e9
    try:
        dt = datetime.fromtimestamp(sec)
    except (OSError, OverflowError, ValueError):
        return "—"
    if millis:
        return dt.strftime("%H:%M:%S.%f")[:-3]
    return dt.strftime("%H:%M:%S")


def format_playhead(t_ns: int, t0_ns: int, mode: TimeMode | str) -> str:
    if is_clock_mode(mode):
        return format_clock_hms(int(t_ns), millis=False)
    rel = max(0.0, (int(t_ns) - int(t0_ns)) / 1e9)
    return f"{rel:.3f} s"


def iso_utc(t_ns: int) -> str:
    from datetime import timezone

    dt = datetime.fromtimestamp(t_ns / 1e9, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
