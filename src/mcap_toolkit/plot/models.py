"""Series models for the four plot docks. Built once per open file. Qt-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from mcap_toolkit.image.colors import roi_color_hex
from mcap_toolkit.io.recording import Recording, StructSample
from mcap_toolkit.plot.matlab import COLORORDER
from mcap_toolkit.io.topics import (
    PRESSURE_KEY_HINTS,
    SHUTTER_FIELDS,
    TOPIC_IMAGE_PARAMS,
    TOPIC_MFC_N2,
    TOPIC_MFC_O2,
    TOPIC_ROI,
    TOPIC_SHUTTERS,
    furnace_name,
    is_furnace_topic,
)

_PRESSURE_SKIP_TOPICS = frozenset(
    {
        TOPIC_SHUTTERS,
        TOPIC_MFC_O2,
        TOPIC_MFC_N2,
        TOPIC_ROI,
        TOPIC_IMAGE_PARAMS,
        "stage/roi_intensity_diff",
        "stage/mbe/snapshot",
    }
)


@dataclass
class Series:
    key: str
    label: str
    t_ns: np.ndarray
    y: np.ndarray
    step: bool = False
    visible: bool = True
    color: str = COLORORDER[0]


@dataclass
class PlotSpec:
    kind: str
    ylabel: str
    series: list[Series] = field(default_factory=list)
    empty_hint: str = ""


@dataclass
class PlotBundle:
    roi: PlotSpec
    temperature: PlotSpec
    shutter: PlotSpec
    pressure: PlotSpec


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not np.isfinite(value):
            return None
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _series_from_pairs(
    key: str,
    label: str,
    pairs: list[tuple[int, float]],
    *,
    step: bool = False,
    color: str = COLORORDER[0],
    visible: bool = True,
) -> Series | None:
    if not pairs:
        return None
    t = np.asarray([p[0] for p in pairs], dtype=np.int64)
    y = np.asarray([p[1] for p in pairs], dtype=np.float64)
    return Series(key=key, label=label, t_ns=t, y=y, step=step, visible=visible, color=color)


def _norm_topic(topic: str) -> str:
    return str(topic or "").lstrip("/")


def _samples_for(recording: Recording, *names: str) -> list[StructSample]:
    by = recording.samples_by_topic
    want = {_norm_topic(n) for n in names}
    for topic, samples in by.items():
        if _norm_topic(topic) in want:
            return samples
    return []


def _extract_numeric_field(samples: list[StructSample], field: str) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    want = field.lower()
    for sample in samples:
        val = _as_float(sample.fields.get(field))
        if val is None:
            for key, raw in sample.fields.items():
                if str(key).lower() == want:
                    val = _as_float(raw)
                    break
        if val is None:
            continue
        out.append((sample.t_ns, val))
    return out


def stream_points_from_sample(topic: str, t_ns: int, fields: dict[str, Any]) -> list[tuple]:
    """Turn one struct sample into (kind, key, label, color, step, t_ns, y) points."""
    topic_n = _norm_topic(topic)
    t_ns = int(t_ns)
    out: list[tuple] = []
    if topic_n.endswith("roi_intensity") and "diff" not in topic_n:
        palette = ["#00ff00", "#ff3c3c", "#00c8ff", "#ffff00", "#ff00ff", "#ff8000"]
        for key, raw in fields.items():
            if not str(key).startswith("roi_"):
                continue
            try:
                idx = int(str(key).split("_", 1)[1])
            except ValueError:
                continue
            val = _as_float(raw)
            if val is None:
                continue
            color = roi_color_hex(idx) if idx <= 64 else palette[(idx - 1) % len(palette)]
            out.append(("roi", str(key), str(key), color, False, t_ns, val))
        return out
    if is_furnace_topic(topic_n):
        val = _as_float(fields.get("pv"))
        if val is None:
            for key, raw in fields.items():
                if str(key).lower() == "pv":
                    val = _as_float(raw)
                    break
        if val is not None:
            name = furnace_name(topic_n)
            color = COLORORDER[sum(ord(c) for c in name) % len(COLORORDER)]
            out.append(("temperature", f"furnace/{name}", name, color, False, t_ns, val))
        return out
    if topic_n == _norm_topic(TOPIC_SHUTTERS) or topic_n.endswith("mbe/shutters"):
        for i, field in enumerate(SHUTTER_FIELDS):
            val = _as_float(fields.get(field))
            if val is None:
                continue
            out.append(
                (
                    "shutter",
                    f"shutter/{field}",
                    field,
                    COLORORDER[i % len(COLORORDER)],
                    True,
                    t_ns,
                    val,
                )
            )
        return out
    for topic_mfc, label in ((TOPIC_MFC_O2, "mfc_o2_valve_4"), (TOPIC_MFC_N2, "mfc_n2_valve_4")):
        if topic_n != _norm_topic(topic_mfc):
            continue
        val = _as_float(fields.get("valve_state_4"))
        if val is None:
            continue
        color = COLORORDER[5] if "o2" in topic_n else COLORORDER[0]
        out.append(("shutter", f"{topic_mfc}/valve_state_4", label, color, True, t_ns, val))
    return out


def _build_roi(recording: Recording) -> PlotSpec:
    samples = _samples_for(recording, TOPIC_ROI)
    if not samples:
        for topic, bucket in recording.samples_by_topic.items():
            key = _norm_topic(topic)
            if key.endswith("roi_intensity") and "diff" not in key:
                samples = bucket
                break
    max_idx = 0
    for sample in samples:
        count = sample.fields.get("roi_count")
        try:
            max_idx = max(max_idx, int(count or 0))
        except (TypeError, ValueError):
            pass
        for key in sample.fields:
            if key.startswith("roi_"):
                try:
                    max_idx = max(max_idx, int(key.split("_", 1)[1]))
                except ValueError:
                    continue
    series: list[Series] = []
    palette = ["#00ff00", "#ff3c3c", "#00c8ff", "#ffff00", "#ff00ff", "#ff8000"]
    for i in range(1, max(max_idx, 0) + 1):
        field = f"roi_{i}"
        pairs = _extract_numeric_field(samples, field)
        item = _series_from_pairs(
            field,
            field,
            pairs,
            color=roi_color_hex(i) if i <= 64 else palette[(i - 1) % len(palette)],
        )
        if item is not None:
            series.append(item)
    return PlotSpec(
        kind="roi",
        ylabel="ROI Intensity",
        series=series,
        empty_hint="" if series else "No ROI traces",
    )


def _build_temperature(recording: Recording) -> PlotSpec:
    series: list[Series] = []
    furnace_topics = sorted(
        t for t in recording.samples_by_topic if is_furnace_topic(_norm_topic(t))
    )
    for topic in furnace_topics:
        name = furnace_name(_norm_topic(topic))
        pairs = _extract_numeric_field(recording.samples_by_topic[topic], "pv")
        item = _series_from_pairs(
            f"furnace/{name}",
            name,
            pairs,
            color=COLORORDER[sum(ord(c) for c in name) % len(COLORORDER)],
        )
        if item is not None:
            series.append(item)
    return PlotSpec(
        kind="temperature",
        ylabel="T (°C)",
        series=series,
        empty_hint="" if series else "No temperature traces",
    )


def _build_shutter(recording: Recording) -> PlotSpec:
    series: list[Series] = []
    shutter_samples = _samples_for(recording, TOPIC_SHUTTERS)
    for i, field in enumerate(SHUTTER_FIELDS):
        pairs = _extract_numeric_field(shutter_samples, field)
        item = _series_from_pairs(
            f"shutter/{field}",
            field,
            pairs,
            step=True,
            color=COLORORDER[i % len(COLORORDER)],
        )
        if item is not None:
            series.append(item)
    for topic, label in ((TOPIC_MFC_O2, "mfc_o2_valve_4"), (TOPIC_MFC_N2, "mfc_n2_valve_4")):
        pairs = _extract_numeric_field(_samples_for(recording, topic), "valve_state_4")
        item = _series_from_pairs(
            f"{topic}/valve_state_4",
            label,
            pairs,
            step=True,
            color=COLORORDER[5] if "o2" in topic else COLORORDER[0],
        )
        if item is not None:
            series.append(item)
    return PlotSpec(
        kind="shutter",
        ylabel="Shutter Status",
        series=series,
        empty_hint="" if series else "No shutter traces",
    )


def _key_looks_like_pressure(name: str) -> bool:
    n = name.lower().replace("-", "_")
    if n in {"pv", "tick", "frame_id", "timestamp", "opc_timestamp", "opc_datetime"}:
        return False
    for hint in PRESSURE_KEY_HINTS:
        if hint in n:
            return True
    if n in {"ig", "pg"}:
        return True
    return False


def _topic_looks_like_pressure(topic: str) -> bool:
    t = topic.lower()
    if topic in _PRESSURE_SKIP_TOPICS or is_furnace_topic(topic) or t.startswith("image/"):
        return False
    for hint in PRESSURE_KEY_HINTS:
        if hint in t:
            return True
    if "pressure" in t or t.endswith("/ig") or t.endswith("/pg"):
        return True
    return False


def _build_pressure(recording: Recording) -> PlotSpec:
    series: list[Series] = []
    color_i = 0
    for topic, samples in sorted(recording.samples_by_topic.items()):
        if (
            topic in _PRESSURE_SKIP_TOPICS
            or is_furnace_topic(topic)
            or topic.startswith("image/")
        ):
            continue
        topic_hit = _topic_looks_like_pressure(topic)
        keys: set[str] = set()
        for sample in samples[:50]:
            keys.update(str(k) for k in sample.fields)
        candidate_fields = [k for k in sorted(keys) if _key_looks_like_pressure(k)]
        if not candidate_fields and topic_hit:
            candidate_fields = [
                k
                for k in sorted(keys)
                if k not in {"tick", "frame_id", "timestamp", "opc_timestamp", "opc_datetime"}
            ]
        for field in candidate_fields:
            pairs = _extract_numeric_field(samples, field)
            label = field if topic_hit and len(candidate_fields) == 1 else f"{topic}:{field}"
            item = _series_from_pairs(
                f"{topic}/{field}",
                label,
                pairs,
                color=COLORORDER[color_i % len(COLORORDER)],
            )
            if item is not None:
                series.append(item)
                color_i += 1
    hint = "" if series else "This file has no pressure topic"
    return PlotSpec(kind="pressure", ylabel="Pressure (torr)", series=series, empty_hint=hint)


def roi_count_from_fields(fields: dict[str, Any]) -> int:
    n = 0
    count = fields.get("roi_count")
    try:
        n = int(count or 0)
    except (TypeError, ValueError):
        n = 0
    for key in fields:
        if not str(key).startswith("roi_"):
            continue
        try:
            n = max(n, int(str(key).split("_", 1)[1]))
        except ValueError:
            continue
    return n


def skeleton_metas(plot_topics: list[str], *, roi_count: int = 0) -> list[tuple]:
    """Legend rows from topic names / known fields. No samples required."""
    metas: list[tuple] = []
    seen: set[str] = set()
    for topic in plot_topics:
        n = _norm_topic(topic)
        if n.endswith("roi_intensity") and "diff" not in n:
            for i in range(1, max(int(roi_count), 0) + 1):
                key = f"roi_{i}"
                if key in seen:
                    continue
                seen.add(key)
                metas.append(("roi", key, key, roi_color_hex(i), False))
            continue
        if is_furnace_topic(n):
            name = furnace_name(n)
            key = f"furnace/{name}"
            if key in seen:
                continue
            seen.add(key)
            color = COLORORDER[sum(ord(c) for c in name) % len(COLORORDER)]
            metas.append(("temperature", key, name, color, False))
            continue
        if n == _norm_topic(TOPIC_SHUTTERS) or n.endswith("mbe/shutters"):
            for i, field in enumerate(SHUTTER_FIELDS):
                key = f"shutter/{field}"
                if key in seen:
                    continue
                seen.add(key)
                metas.append(("shutter", key, field, COLORORDER[i % len(COLORORDER)], True))
            continue
        for topic_mfc, label in ((TOPIC_MFC_O2, "mfc_o2_valve_4"), (TOPIC_MFC_N2, "mfc_n2_valve_4")):
            if n != _norm_topic(topic_mfc):
                continue
            key = f"{topic_mfc}/valve_state_4"
            if key in seen:
                continue
            seen.add(key)
            color = COLORORDER[5] if "o2" in n else COLORORDER[0]
            metas.append(("shutter", key, label, color, True))
    return metas


def bundle_from_metas(metas: list[tuple], *, loading: bool = False) -> PlotBundle:
    by_kind: dict[str, list[Series]] = {"roi": [], "temperature": [], "shutter": [], "pressure": []}
    for kind, key, label, color, step in metas:
        bucket = by_kind.setdefault(kind, [])
        bucket.append(
            Series(
                key=str(key),
                label=str(label),
                t_ns=np.empty(0, dtype=np.int64),
                y=np.empty(0, dtype=np.float64),
                step=bool(step),
                color=str(color),
            )
        )
    load_hint = "Loading traces…" if loading else ""
    roi = by_kind["roi"]
    temp = by_kind["temperature"]
    shut = by_kind["shutter"]
    return PlotBundle(
        roi=PlotSpec(
            kind="roi",
            ylabel="ROI Intensity",
            series=roi,
            empty_hint="" if roi else (load_hint or "No ROI traces"),
        ),
        temperature=PlotSpec(
            kind="temperature",
            ylabel="T (°C)",
            series=temp,
            empty_hint="" if temp else (load_hint or "No temperature traces"),
        ),
        shutter=PlotSpec(
            kind="shutter",
            ylabel="Shutter Status",
            series=shut,
            empty_hint="" if shut else (load_hint or "No shutter traces"),
        ),
        pressure=PlotSpec(kind="pressure", ylabel="Pressure (torr)"),
    )


def empty_plot_bundle(*, loading: bool = False) -> PlotBundle:
    hint = "Loading traces…" if loading else ""
    return PlotBundle(
        roi=PlotSpec(kind="roi", ylabel="ROI Intensity", empty_hint=hint),
        temperature=PlotSpec(kind="temperature", ylabel="T (°C)", empty_hint=hint),
        shutter=PlotSpec(kind="shutter", ylabel="Shutter Status", empty_hint=hint),
        pressure=PlotSpec(kind="pressure", ylabel="Pressure (torr)", empty_hint=hint),
    )


def build_plot_bundle(recording: Recording) -> PlotBundle:
    return PlotBundle(
        roi=_build_roi(recording),
        temperature=_build_temperature(recording),
        shutter=_build_shutter(recording),
        pressure=_build_pressure(recording),
    )
