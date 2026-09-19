"""Full-resolution series live in the open worker. The GUI only gets ~2k display points."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from mcap_toolkit.io.recording import StructSample
from mcap_toolkit.plot.models import Series, stream_points_from_sample

DISPLAY_MAX = 2000


@dataclass
class SeriesBuf:
    kind: str
    key: str
    label: str
    color: str
    step: bool = False
    expected: int = 0
    full_t: list[int] = field(default_factory=list)
    full_y: list[float] = field(default_factory=list)
    pending_t: list[int] = field(default_factory=list)
    pending_y: list[float] = field(default_factory=list)
    emitted: int = 0
    last_emit_t: int | None = None

    def add(self, t_ns: int, y: float) -> None:
        t_ns = int(t_ns)
        y = float(y)
        self.full_t.append(t_ns)
        self.full_y.append(y)
        if self._should_emit():
            self.pending_t.append(t_ns)
            self.pending_y.append(y)
            self.emitted += 1
            self.last_emit_t = t_ns

    def _should_emit(self) -> bool:
        n = len(self.full_t)
        if n <= 1:
            return True
        cap = DISPLAY_MAX
        exp = self.expected if self.expected > 0 else n
        want = min(cap, max(exp, 1))
        prev = (n - 2) * want // max(exp, 1)
        cur = (n - 1) * want // max(exp, 1)
        return cur > prev

    def emit_last(self) -> None:
        if not self.full_t:
            return
        t_ns = self.full_t[-1]
        if self.last_emit_t == t_ns:
            return
        self.pending_t.append(t_ns)
        self.pending_y.append(self.full_y[-1])
        self.emitted += 1
        self.last_emit_t = t_ns

    def as_series(self, *, visible: bool = True, label: str | None = None) -> Series:
        return Series(
            key=self.key,
            label=label if label is not None else self.label,
            t_ns=np.asarray(self.full_t, dtype=np.int64),
            y=np.asarray(self.full_y, dtype=np.float64),
            step=self.step,
            visible=visible,
            color=self.color,
        )


class PlotStore:
    def __init__(
        self,
        *,
        struct_counts: dict[str, int] | None = None,
        roi_geoms: list[tuple[int, list[dict[str, Any]]]] | None = None,
    ) -> None:
        self.series: dict[str, SeriesBuf] = {}
        self.struct_counts = dict(struct_counts or {})
        self.roi_geoms = roi_geoms if roi_geoms is not None else []
        self.n_messages = 0
        self._capture_geom = True

    def expected_for(self, topic: str) -> int:
        if topic in self.struct_counts:
            return int(self.struct_counts[topic])
        want = str(topic or "").lstrip("/")
        for key, n in self.struct_counts.items():
            if str(key).lstrip("/") == want:
                return int(n)
        return 0

    def ingest(self, topic: str, sample: StructSample, *, capture_geom: bool = True) -> None:
        self.n_messages += 1
        points = stream_points_from_sample(topic, sample.t_ns, sample.fields)
        expected = self.expected_for(topic)
        for kind, key, label, color, step, t_ns, y in points:
            buf = self.series.get(key)
            if buf is None:
                buf = SeriesBuf(
                    kind=str(kind),
                    key=str(key),
                    label=str(label),
                    color=str(color),
                    step=bool(step),
                    expected=expected,
                )
                self.series[key] = buf
            buf.add(int(t_ns), float(y))
        if capture_geom and self._capture_geom:
            topic_n = str(topic or "").lstrip("/")
            if topic_n.endswith("roi_intensity") and "diff" not in topic_n:
                raw = sample.fields.get("rois")
                if isinstance(raw, list) and raw:
                    geom = [item for item in raw if isinstance(item, dict)]
                    if geom:
                        self.roi_geoms.append((int(sample.t_ns), geom))

    def take_display(self) -> list[tuple]:
        out: list[tuple] = []
        for buf in self.series.values():
            if not buf.pending_t:
                continue
            out.append(
                (
                    buf.kind,
                    buf.key,
                    buf.label,
                    buf.color,
                    buf.step,
                    buf.pending_t,
                    buf.pending_y,
                )
            )
            buf.pending_t = []
            buf.pending_y = []
        return out

    def finish(self) -> None:
        for buf in self.series.values():
            buf.emit_last()
        self.roi_geoms.sort(key=lambda item: item[0])

    def series_for_csv(self, keys: list[str], *, labels: dict[str, str], visible: dict[str, bool]) -> list[Series]:
        out: list[Series] = []
        for key in keys:
            buf = self.series.get(key)
            if buf is None:
                continue
            out.append(
                buf.as_series(
                    visible=visible.get(key, True),
                    label=labels.get(key, buf.label),
                )
            )
        return out
