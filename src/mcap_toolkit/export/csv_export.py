"""CSV export of visible series at full resolution of the current time range."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from mcap_toolkit.plot.models import Series
from mcap_toolkit.plot.time_axis import iso_utc


def csv_headers(kind: str, series: Sequence[Series]) -> list[str]:
    """Stable header list used by tests and writers."""
    names = [s.label or s.key for s in series]
    return ["time_rel_s", "time_iso", *names]


def write_series_csv(
    path: str | Path,
    series: Sequence[Series],
    *,
    t0_ns: int,
    x_min_ns: int,
    x_max_ns: int,
) -> None:
    path = Path(path)
    visible = [s for s in series if s.visible]
    headers = csv_headers(visible[0].key.split("/")[0] if visible else "plot", visible)
    # Union of timestamps in range; NaN where a series has no sample.
    stamps: set[int] = set()
    indexed: list[dict[int, float]] = []
    for s in visible:
        lut: dict[int, float] = {}
        t = np.asarray(s.t_ns)
        y = np.asarray(s.y)
        for ti, yi in zip(t.tolist(), y.tolist(), strict=False):
            ti_i = int(ti)
            if x_min_ns <= ti_i <= x_max_ns:
                lut[ti_i] = float(yi)
                stamps.add(ti_i)
        indexed.append(lut)
    rows_t = sorted(stamps)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for t_ns in rows_t:
            rel = (t_ns - t0_ns) / 1e9
            row: list[object] = [f"{rel:.9f}", iso_utc(t_ns)]
            for lut in indexed:
                val = lut.get(t_ns)
                row.append("" if val is None else f"{val:.10g}")
            writer.writerow(row)
