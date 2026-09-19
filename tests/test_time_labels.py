from datetime import datetime

from mcap_toolkit.plot.time_axis import (
    TimeMode,
    clock_tick_positions,
    format_clock_hms,
    format_playhead,
    playhead_ns_from_ratio,
    rel_seconds_to_ns,
    xlabel_for_mode,
    x_values,
)
import numpy as np


def test_relative_xlabel_is_seconds_from_zero() -> None:
    assert xlabel_for_mode(TimeMode.RELATIVE) == "Time (sec.)"
    assert xlabel_for_mode("relative") == "Time (sec.)"


def test_absolute_xlabel_is_clock() -> None:
    assert xlabel_for_mode(TimeMode.ABSOLUTE) == "Time"
    assert xlabel_for_mode("absolute") == "Time"


def test_relative_x_starts_at_zero() -> None:
    t0 = 1_000_000_000
    t = np.array([t0, t0 + 2_500_000_000], dtype=np.int64)
    x = x_values(t, t0, TimeMode.RELATIVE)
    assert x[0] == 0.0
    assert abs(x[1] - 2.5) < 1e-9


def test_absolute_x_is_also_seconds_from_zero() -> None:
    t0 = 1_757_000_000_000_000_000
    t = np.array([t0, t0 + 2_500_000_000], dtype=np.int64)
    xr = x_values(t, t0, TimeMode.RELATIVE)
    xa = x_values(t, t0, TimeMode.ABSOLUTE)
    assert np.allclose(xr, xa)
    assert xa[0] == 0.0
    assert abs(xa[1] - 2.5) < 1e-9


def test_absolute_playhead_is_hms() -> None:
    dt = datetime(2026, 9, 17, 14, 32, 5)
    t_ns = int(dt.timestamp() * 1e9)
    text = format_playhead(t_ns, 0, TimeMode.ABSOLUTE)
    assert text.startswith("14:32:05")


def test_absolute_label_follows_sample_wall_clock() -> None:
    dt = datetime(2026, 9, 17, 14, 32, 5)
    t0 = int(dt.timestamp() * 1e9)
    later = rel_seconds_to_ns(t0, 2.0)
    text = format_playhead(later, t0, TimeMode.ABSOLUTE)
    expected = datetime.fromtimestamp(later / 1e9).strftime("%H:%M:%S")
    assert text.startswith(expected)


def test_clock_ticks_land_on_whole_local_seconds() -> None:
    dt = datetime(2026, 9, 17, 14, 32, 5, 400000)
    t0 = int(dt.timestamp() * 1e9)
    ticks = clock_tick_positions(t0, 0.0, 3.0, 1.0)
    assert len(ticks) >= 2
    for x in ticks:
        wall = datetime.fromtimestamp(rel_seconds_to_ns(t0, x) / 1e9)
        us = wall.microsecond
        assert min(us, 1_000_000 - us) < 2000
        assert format_clock_hms(rel_seconds_to_ns(t0, x)).count(":") == 2


def test_relative_playhead_is_seconds() -> None:
    t0 = 10_000_000_000
    text = format_playhead(t0 + 1_250_000_000, t0, TimeMode.RELATIVE)
    assert text == "1.250 s"


def test_seek_ratio_keeps_epoch_nanoseconds() -> None:
    t0 = 1_757_000_000_000_000_000
    t1 = t0 + 10_000_000_000
    assert playhead_ns_from_ratio(t0, t1, 0.0) == t0
    assert playhead_ns_from_ratio(t0, t1, 1.0) == t1
    mid = playhead_ns_from_ratio(t0, t1, 0.5)
    assert mid == t0 + 5_000_000_000
    # Must not collapse to ~0 via float64(t0 + ratio * span).
    assert abs(mid - t0 - 5_000_000_000) == 0


def test_ratio_from_playhead_round_trips() -> None:
    from mcap_toolkit.plot.time_axis import ratio_from_playhead

    t0 = 1_757_000_000_000_000_000
    t1 = t0 + 10_000_000_000
    assert ratio_from_playhead(t0, t1, t0) == 0.0
    assert ratio_from_playhead(t0, t1, t1) == 1.0
    assert abs(ratio_from_playhead(t0, t1, t0 + 5_000_000_000) - 0.5) < 1e-12
    # A raw 0 timestamp must not become ratio 0 on an epoch span via float(t)/span.
    assert ratio_from_playhead(t0, t1, 0) == 0.0
    x = x_values(np.array([t0, t0 + 2_000_000_000], dtype=np.int64), t0)
    assert abs(float(x[0])) < 1e-15
    assert abs(float(x[1]) - 2.0) < 1e-9


def test_time_span_skips_zero_timestamps() -> None:
    from mcap_toolkit.io.mcap_index import _time_span
    from mcap_toolkit.io.recording import StructSample

    t0 = 1_757_000_000_000_000_000
    samples = {
        "stage/mbe/furnace/ti": [
            StructSample(t_ns=0, fields={"pv": 0.0}),
            StructSample(t_ns=t0, fields={"pv": 1.0}),
            StructSample(t_ns=t0 + 10_000_000_000, fields={"pv": 2.0}),
        ]
    }
    span0, span1 = _time_span({}, samples)
    assert span0 == t0
    assert span1 == t0 + 10_000_000_000


def test_time_span_ignores_zero_statistics() -> None:
    from mcap_toolkit.io.mcap_index import _time_span
    from mcap_toolkit.io.recording import StructSample

    t0 = 1_757_000_000_000_000_000
    samples = {
        "stage/mbe/furnace/ti": [
            StructSample(t_ns=t0, fields={"pv": 1.0}),
            StructSample(t_ns=t0 + 10_000_000_000, fields={"pv": 2.0}),
        ]
    }
    span0, span1 = _time_span({}, samples)
    assert span0 == t0
    assert span1 == t0 + 10_000_000_000
    x = x_values(np.array([span0, span1], dtype=np.int64), span0, TimeMode.RELATIVE)
    assert abs(float(x[0])) < 1e-12
    assert abs(float(x[1]) - 10.0) < 1e-9
