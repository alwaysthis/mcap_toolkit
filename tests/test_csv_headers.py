from __future__ import annotations

import numpy as np

from mcap_toolkit.export.csv_export import csv_headers
from mcap_toolkit.plot.models import Series, skeleton_metas


def _s(key: str, label: str | None = None) -> Series:
    return Series(
        key=key,
        label=label or key,
        t_ns=np.array([0, 1], dtype=np.int64),
        y=np.array([1.0, 2.0]),
    )


def test_csv_headers_roi() -> None:
    series = [_s("roi_1"), _s("roi_2")]
    assert csv_headers("roi", series) == ["time_rel_s", "time_iso", "roi_1", "roi_2"]


def test_csv_headers_temperature() -> None:
    series = [_s("furnace/srtop", "srtop"), _s("furnace/ti", "ti")]
    assert csv_headers("temperature", series) == ["time_rel_s", "time_iso", "srtop", "ti"]


def test_csv_headers_shutter() -> None:
    series = [_s("shutter/main", "main"), _s("stage/mbe/mfc_o2/valve_state_4", "mfc_o2_valve_4")]
    assert csv_headers("shutter", series) == [
        "time_rel_s",
        "time_iso",
        "main",
        "mfc_o2_valve_4",
    ]


def test_csv_headers_pressure() -> None:
    series = [_s("stage/pressure/ig", "ig")]
    assert csv_headers("pressure", series) == ["time_rel_s", "time_iso", "ig"]


def test_skeleton_legend_from_topics() -> None:
    metas = skeleton_metas(
        [
            "stage/roi_intensity",
            "stage/mbe/furnace/srtop",
            "stage/mbe/shutters",
            "stage/mbe/mfc_o2",
        ],
        roi_count=2,
    )
    keys = [m[1] for m in metas]
    assert "roi_1" in keys
    assert "roi_2" in keys
    assert "furnace/srtop" in keys
    assert "shutter/main" in keys
    assert "stage/mbe/mfc_o2/valve_state_4" in keys
