"""Recording dataclasses. Qt-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageFrameRef:
    """Index entry: timestamp only. Compressed bytes are loaded lazily from the file."""

    t_ns: int
    format: str = ""
    data: bytes = b""


@dataclass
class ImageTopicIndex:
    topic: str
    display_name: str
    frames: list[ImageFrameRef] = field(default_factory=list)


@dataclass
class StructSample:
    t_ns: int
    fields: dict[str, Any]


@dataclass
class Recording:
    path: str
    t0_ns: int
    t1_ns: int
    image_topics: list[ImageTopicIndex] = field(default_factory=list)
    samples_by_topic: dict[str, list[StructSample]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    plot_topics: list[str] = field(default_factory=list)
    struct_count: int = 0
    struct_counts: dict[str, int] = field(default_factory=dict)
    roi_count: int = 0
    roi_geoms: list[tuple[int, list[dict[str, Any]]]] = field(default_factory=list)
    _jpeg_cache: dict[tuple[str, int], tuple[str, bytes]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _jpeg_order: list[tuple[str, int]] = field(default_factory=list, repr=False, compare=False)
    _file: Any = field(default=None, repr=False, compare=False)
    _reader: Any = field(default=None, repr=False, compare=False)

    def image_topic(self, topic: str) -> ImageTopicIndex | None:
        for item in self.image_topics:
            if item.topic == topic:
                return item
        return None

    def open_reader(self) -> None:
        self.close_reader()
        handle = open(self.path, "rb")
        from mcap.reader import SeekingReader

        self._file = handle
        self._reader = SeekingReader(handle, validate_crcs=False)

    def close_reader(self) -> None:
        self._reader = None
        handle = self._file
        self._file = None
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        self._jpeg_cache.clear()
        self._jpeg_order.clear()

    def fetch_compressed(self, topic: str, t_ns: int) -> tuple[str, bytes] | None:
        key = (topic, int(t_ns))
        hit = self._jpeg_cache.get(key)
        if hit is not None:
            return hit
        from mcap_toolkit.io.mcap_index import read_compressed_at

        try:
            if self._reader is None:
                self.open_reader()
            got = read_compressed_at(self.path, topic, t_ns, reader=self._reader)
            if got is None:
                self.close_reader()
                self.open_reader()
                got = read_compressed_at(self.path, topic, t_ns, reader=self._reader)
        except Exception:
            try:
                self.close_reader()
                self.open_reader()
                got = read_compressed_at(self.path, topic, t_ns, reader=self._reader)
            except Exception:
                return None
        if got is None:
            return None
        self._jpeg_cache[key] = got
        self._jpeg_order.append(key)
        while len(self._jpeg_order) > 24:
            old = self._jpeg_order.pop(0)
            if old != key:
                self._jpeg_cache.pop(old, None)
        return got

    def rois_at(self, t_ns: int) -> list[dict[str, Any]]:
        from mcap_toolkit.io.topics import TOPIC_ROI

        last: list[dict[str, Any]] = []
        geoms = self.roi_geoms
        if geoms:
            for t_geom, geom in geoms:
                if int(t_geom) > int(t_ns):
                    break
                if geom:
                    last = geom
            return last
        for sample in self.samples_by_topic.get(TOPIC_ROI, ()):
            if sample.t_ns > t_ns:
                break
            raw = sample.fields.get("rois")
            if isinstance(raw, list) and raw:
                geom = [item for item in raw if isinstance(item, dict)]
                if geom:
                    last = geom
        return last


def frame_at_or_before(frames: list[ImageFrameRef], t_ns: int) -> ImageFrameRef | None:
    if not frames:
        return None
    lo, hi = 0, len(frames) - 1
    ans: ImageFrameRef | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if frames[mid].t_ns <= t_ns:
            ans = frames[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    return ans if ans is not None else frames[0]


def next_frame_time(frames: list[ImageFrameRef], t_ns: int) -> int | None:
    lo, hi = 0, len(frames)
    while lo < hi:
        mid = (lo + hi) // 2
        if frames[mid].t_ns <= t_ns:
            lo = mid + 1
        else:
            hi = mid
    if lo < len(frames):
        return frames[lo].t_ns
    return None


def prev_frame_time(frames: list[ImageFrameRef], t_ns: int) -> int | None:
    lo, hi = 0, len(frames)
    while lo < hi:
        mid = (lo + hi) // 2
        if frames[mid].t_ns < t_ns:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return None
    return frames[lo - 1].t_ns
