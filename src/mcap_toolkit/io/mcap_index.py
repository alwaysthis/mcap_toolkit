"""Index an MCAP once. Skip image payloads; decode JPEG only when a frame is shown. No Qt."""

from __future__ import annotations

from pathlib import Path

from mcap.reader import SeekingReader, make_reader
from mcap.records import MessageIndex
from mcap.stream_reader import StreamReader

from mcap_toolkit.io.decode import (
    decode_compressed_image_bytes,
    decode_json_bytes,
    decode_struct_bytes_skip,
    schema_looks_like_image,
)
from mcap_toolkit.io.recording import ImageFrameRef, ImageTopicIndex, Recording, StructSample
from mcap_toolkit.io.topics import TOPIC_IMAGE_PARAMS, image_display_name, image_topic_sort_key

_SKIP_STRUCT_KEYS = frozenset(
    {"timestamp", "opc_timestamp", "opc_datetime", "tick", "frame_id"}
)

# High-rate topics Foxglove would not subscribe to just to open the file.
_SKIP_DECODE_TOPICS = frozenset(
    {
        TOPIC_IMAGE_PARAMS,
        "stage/mbe/snapshot",
        "stage/roi_intensity_diff",
    }
)

_SKIP_STRUCT_KEYS = frozenset(
    {"timestamp", "opc_timestamp", "opc_datetime", "tick", "frame_id"}
)


def _schema_name(schema: object | None) -> str:
    if schema is None:
        return ""
    return str(getattr(schema, "name", "") or "")


def _encoding(schema: object | None, channel: object | None) -> str:
    for obj in (channel, schema):
        if obj is None:
            continue
        enc = getattr(obj, "message_encoding", None) or getattr(obj, "encoding", None)
        if enc:
            return str(enc)
    return ""


def _channel_is_image(channel: object, schema: object | None) -> bool:
    topic = str(getattr(channel, "topic", "") or "")
    return schema_looks_like_image(_schema_name(schema), topic)


def _positive_times(times) -> list[int]:
    return [int(t) for t in times if int(t) > 0]


def _time_span(
    image_times: dict[str, list[int]],
    samples: dict[str, list[StructSample]],
    extra_times: dict[str, list[int]] | None = None,
) -> tuple[int, int]:
    """Min/max log time from indexed data — never trust empty/zero MCAP statistics."""
    t0: int | None = None
    t1: int | None = None
    for times in image_times.values():
        valid = _positive_times(times)
        if not valid:
            continue
        lo = min(valid)
        hi = max(valid)
        t0 = lo if t0 is None else min(t0, lo)
        t1 = hi if t1 is None else max(t1, hi)
    for topic_samples in samples.values():
        valid = _positive_times(s.t_ns for s in topic_samples)
        if not valid:
            continue
        lo = min(valid)
        hi = max(valid)
        t0 = lo if t0 is None else min(t0, lo)
        t1 = hi if t1 is None else max(t1, hi)
    if extra_times:
        for times in extra_times.values():
            valid = _positive_times(times)
            if not valid:
                continue
            lo = min(valid)
            hi = max(valid)
            t0 = lo if t0 is None else min(t0, lo)
            t1 = hi if t1 is None else max(t1, hi)
    if t0 is None or t1 is None:
        return 0, 0
    return int(t0), int(t1)


def _roi_count_from_fields(fields: dict) -> int:
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


def _roi_geom_from_fields(fields: dict) -> list[dict]:
    raw = fields.get("rois")
    if not isinstance(raw, list) or not raw:
        return []
    return [item for item in raw if isinstance(item, dict)]


def _peek_roi_count(path: Path, topics: list[str]) -> int:
    roi_topics = [
        t
        for t in topics
        if str(t).lstrip("/").endswith("roi_intensity") and "diff" not in str(t).lstrip("/")
    ]
    if not roi_topics:
        return 0
    with path.open("rb") as handle:
        reader = SeekingReader(handle, validate_crcs=False)
        try:
            for schema, channel, message in reader.iter_messages(
                topics=roi_topics, log_time_order=False
            ):
                samples: dict[str, list[StructSample]] = {}
                warnings: list[str] = []
                _append_struct(
                    samples,
                    channel.topic,
                    int(message.log_time),
                    message.data,
                    _encoding(schema, channel),
                    warnings,
                )
                for items in samples.values():
                    for sample in items:
                        n = _roi_count_from_fields(sample.fields)
                        if n:
                            return n
                break
        except Exception:
            return 0
    return 0


def _as_topic_map(times_by_topic: dict[str, list[int]]) -> list[ImageTopicIndex]:
    out: list[ImageTopicIndex] = []
    for topic, times in times_by_topic.items():
        times = sorted(t for t in times if int(t) > 0)
        frames = [ImageFrameRef(t_ns=t) for t in times]
        out.append(
            ImageTopicIndex(
                topic=topic,
                display_name=image_display_name(topic),
                frames=frames,
            )
        )
    out.sort(key=lambda t: image_topic_sort_key(t.topic))
    return out


def _read_message_indexes(stream, summary, channel_ids: set[int] | None = None) -> dict[str, list[int]]:
    """Timestamps only — does not decompress chunk payloads."""
    id_to_topic: dict[int, str] = {}
    for cid, channel in summary.channels.items():
        if channel_ids is not None and cid not in channel_ids:
            continue
        id_to_topic[cid] = channel.topic
    acc: dict[str, list[int]] = {topic: [] for topic in id_to_topic.values()}
    if not id_to_topic:
        return acc
    has_index = any(chunk.message_index_offsets for chunk in summary.chunk_indexes)
    if not has_index:
        return {}
    for chunk in summary.chunk_indexes:
        for cid, offset in chunk.message_index_offsets.items():
            if cid not in id_to_topic:
                continue
            stream.seek(int(offset))
            record = next(
                StreamReader(stream, skip_magic=True, record_size_limit=64 * 2**20).records,
                None,
            )
            if not isinstance(record, MessageIndex):
                continue
            topic = id_to_topic.get(record.channel_id)
            if not topic:
                continue
            bucket = acc.setdefault(topic, [])
            for timestamp, _off in record.records:
                bucket.append(int(timestamp))
    return acc


def _should_decode_struct(topic: str) -> bool:
    if topic in _SKIP_DECODE_TOPICS or topic.startswith("image/"):
        return False
    return True


def _append_struct(
    samples: dict[str, list[StructSample]],
    topic: str,
    t_ns: int,
    data: bytes,
    encoding: str,
    warnings: list[str],
) -> None:
    try:
        if encoding.lower() in {"json", "jsonschema"}:
            parsed = decode_json_bytes(data)
        else:
            try:
                parsed = decode_struct_bytes_skip(data, _SKIP_STRUCT_KEYS)
            except Exception:
                parsed = decode_json_bytes(data)
        if not isinstance(parsed, dict):
            parsed = {"value": parsed}
        if encoding.lower() in {"json", "jsonschema"}:
            parsed = {k: v for k, v in parsed.items() if k not in _SKIP_STRUCT_KEYS}
        samples.setdefault(topic, []).append(StructSample(t_ns=t_ns, fields=parsed))
    except Exception as exc:
        warnings.append(f"{topic}: failed to parse message at t={t_ns}: {exc}")


def _linear_scan(path: Path) -> Recording:
    image_times: dict[str, list[int]] = {}
    samples: dict[str, list[StructSample]] = {}
    warnings: list[str] = []
    t_min: int | None = None
    t_max: int | None = None
    with path.open("rb") as handle:
        reader = make_reader(handle)
        try:
            for schema, channel, message in reader.iter_messages(log_time_order=False):
                topic = str(getattr(channel, "topic", "") or "")
                t_ns = int(getattr(message, "log_time", 0) or 0)
                if t_min is None or t_ns < t_min:
                    t_min = t_ns
                if t_max is None or t_ns > t_max:
                    t_max = t_ns
                if schema_looks_like_image(_schema_name(schema), topic):
                    image_times.setdefault(topic, []).append(t_ns)
                    continue
                if not _should_decode_struct(topic):
                    continue
                _append_struct(
                    samples,
                    topic,
                    t_ns,
                    message.data,
                    _encoding(schema, channel),
                    warnings,
                )
        except Exception as exc:
            warnings.append(f"truncated or corrupt MCAP: {exc}")
    for topic_samples in samples.values():
        topic_samples.sort(key=lambda s: s.t_ns)
    roi_count = 0
    roi_geoms: list[tuple[int, list]] = []
    for topic, topic_samples in samples.items():
        key = str(topic).lstrip("/")
        if not (key.endswith("roi_intensity") and "diff" not in key):
            continue
        for sample in topic_samples:
            roi_count = max(roi_count, _roi_count_from_fields(sample.fields))
            geom = _roi_geom_from_fields(sample.fields)
            if geom:
                roi_geoms.append((int(sample.t_ns), geom))
    t0 = int(t_min or 0)
    t1 = int(t_max or t0)
    return Recording(
        path=str(path),
        t0_ns=t0,
        t1_ns=t1,
        image_topics=_as_topic_map(image_times),
        samples_by_topic=samples,
        plot_topics=sorted(samples.keys()),
        warnings=warnings,
        struct_count=sum(len(v) for v in samples.values()),
        struct_counts={t: len(v) for t, v in samples.items()},
        roi_count=roi_count,
        roi_geoms=roi_geoms,
    )


def index_recording(path: str | Path) -> Recording:
    """Foxglove-style first pass: summary + message indexes, no payload decode."""
    path = Path(path)
    with path.open("rb") as handle:
        reader = SeekingReader(handle, validate_crcs=False)
        try:
            summary = reader.get_summary()
        except Exception:
            summary = None
        if summary is None or not summary.chunk_indexes:
            return _linear_scan(path)

        image_ids: set[int] = set()
        struct_ids: set[int] = set()
        plot_topics: list[str] = []
        for cid, channel in summary.channels.items():
            schema = summary.schemas.get(channel.schema_id) if channel.schema_id else None
            if _channel_is_image(channel, schema):
                image_ids.add(cid)
            elif _should_decode_struct(channel.topic):
                struct_ids.add(cid)
                plot_topics.append(channel.topic)

        times = _read_message_indexes(handle, summary)
        if image_ids and not any(
            times.get(summary.channels[cid].topic) for cid in image_ids if cid in summary.channels
        ):
            rec = _linear_scan(path)
            return rec

        image_times = {
            summary.channels[cid].topic: times.get(summary.channels[cid].topic, [])
            for cid in image_ids
            if cid in summary.channels
        }
        extra_times = {
            summary.channels[cid].topic: times.get(summary.channels[cid].topic, [])
            for cid in struct_ids
            if cid in summary.channels
        }
        t0, t1 = _time_span(image_times, {}, extra_times)
        plot_topics = sorted(set(plot_topics))
        struct_counts = {topic: len(ts) for topic, ts in extra_times.items()}
        rec = Recording(
            path=str(path),
            t0_ns=t0,
            t1_ns=t1,
            image_topics=_as_topic_map(image_times),
            samples_by_topic={},
            plot_topics=plot_topics,
            warnings=[],
            struct_count=sum(struct_counts.values()),
            struct_counts=struct_counts,
            roi_count=0,
            roi_geoms=[],
        )
    rec.roi_count = _peek_roi_count(path, rec.plot_topics)
    return rec


def iter_struct_batches(
    path: str | Path,
    topics: list[str],
    *,
    batch_size: int = 400,
    warnings: list[str] | None = None,
):
    """Yield plot-topic samples in chunks so the UI can draw while decoding."""
    path = Path(path)
    warn = warnings if warnings is not None else []
    topic_list = list(topics)
    if not topic_list:
        with path.open("rb") as handle:
            reader = SeekingReader(handle, validate_crcs=False)
            try:
                summary = reader.get_summary()
            except Exception:
                summary = None
            if summary is not None:
                topic_list = [
                    ch.topic
                    for ch in summary.channels.values()
                    if not _channel_is_image(
                        ch, summary.schemas.get(ch.schema_id) if ch.schema_id else None
                    )
                    and _should_decode_struct(ch.topic)
                ]
    yielded = False
    if topic_list:
        batch: dict[str, list[StructSample]] = {}
        count = 0
        with path.open("rb") as handle:
            reader = SeekingReader(handle, validate_crcs=False)
            try:
                for schema, channel, message in reader.iter_messages(
                    topics=topic_list, log_time_order=False
                ):
                    _append_struct(
                        batch,
                        channel.topic,
                        int(message.log_time),
                        message.data,
                        _encoding(schema, channel),
                        warn,
                    )
                    count += 1
                    if count >= batch_size:
                        yield batch
                        yielded = True
                        batch = {}
                        count = 0
            except Exception as exc:
                warn.append(f"truncated or corrupt MCAP: {exc}")
        if batch:
            yield batch
            yielded = True
    if not yielded:
        fallback = _linear_scan(path)
        warn.extend(fallback.warnings)
        if fallback.samples_by_topic:
            yield fallback.samples_by_topic


def fill_struct_samples(recording: Recording) -> None:
    """Second pass: decode only plot topics (skip image payloads and per-frame params)."""
    if recording.samples_by_topic:
        return
    samples: dict[str, list[StructSample]] = {}
    warnings: list[str] = []
    for batch in iter_struct_batches(recording.path, list(recording.plot_topics), warnings=warnings):
        for topic, items in batch.items():
            samples.setdefault(topic, []).extend(items)
    for topic_samples in samples.values():
        topic_samples.sort(key=lambda s: s.t_ns)
    if not samples:
        fallback = _linear_scan(Path(recording.path))
        samples = fallback.samples_by_topic
        warnings.extend(fallback.warnings)
        if fallback.image_topics and not recording.image_topics:
            recording.image_topics = fallback.image_topics
        if fallback.plot_topics:
            recording.plot_topics = sorted(set(recording.plot_topics) | set(fallback.plot_topics))
    recording.samples_by_topic = samples
    recording.warnings.extend(warnings)
    t0, t1 = _time_span(
        {item.topic: [f.t_ns for f in item.frames] for item in recording.image_topics},
        samples,
    )
    if t0 > 0 and (recording.t0_ns <= 0 or t0 < recording.t0_ns):
        recording.t0_ns = t0
    if t1 > recording.t1_ns:
        recording.t1_ns = t1


def load_recording(path: str | Path) -> Recording:
    path = Path(path)
    rec = index_recording(path)
    if rec.image_topics or rec.plot_topics or rec.t1_ns > rec.t0_ns:
        if not rec.samples_by_topic:
            fill_struct_samples(rec)
        return rec
    return _linear_scan(path)


def _decode_compressed_message(encoding: str, data: bytes) -> tuple[str, bytes] | None:
    if encoding.lower() in {"json", "jsonschema"}:
        payload = decode_json_bytes(data)
        if not isinstance(payload, dict):
            return None
        fmt = str(payload.get("format") or "jpeg")
        raw = payload.get("data") or b""
        if isinstance(raw, str):
            import base64

            raw = base64.b64decode(raw)
        return fmt, bytes(raw)
    fmt, blob = decode_compressed_image_bytes(data)
    return fmt or "jpeg", blob


def read_compressed_from_reader(reader, topic: str, t_ns: int) -> tuple[str, bytes] | None:
    t_ns = int(t_ns)
    # Inclusive start, exclusive end. First window is an exact indexed timestamp.
    windows = (
        (t_ns, t_ns + 1),
        (max(0, t_ns - 1), t_ns + 2),
        (t_ns, t_ns + 5_000_000),
        (max(0, t_ns - 1_000_000), t_ns + 1),
    )
    for start, end in windows:
        best = None
        best_dt: int | None = None
        for schema, channel, message in reader.iter_messages(
            topics=[topic],
            start_time=int(start),
            end_time=int(end),
            log_time_order=False,
        ):
            dt = abs(int(message.log_time) - t_ns)
            if best_dt is not None and dt >= best_dt:
                continue
            encoding = _encoding(schema, channel)
            decoded = _decode_compressed_message(encoding, message.data)
            if decoded is None:
                continue
            best = decoded
            best_dt = dt
            if dt == 0:
                return best
        if best is not None:
            return best
    return None


def read_compressed_at(path: str | Path, topic: str, t_ns: int, reader=None) -> tuple[str, bytes] | None:
    """Load one CompressedImage by timestamp (exclusive end = t_ns+1)."""
    if reader is not None:
        return read_compressed_from_reader(reader, topic, t_ns)
    path = Path(path)
    with path.open("rb") as handle:
        seeking = SeekingReader(handle, validate_crcs=False)
        return read_compressed_from_reader(seeking, topic, t_ns)


def iter_compressed_topic(path: str | Path, topic: str):
    """Yield (t_ns, format, jpeg/png bytes) in file order — for video export."""
    path = Path(path)
    with path.open("rb") as handle:
        reader = make_reader(handle)
        for schema, channel, message in reader.iter_messages(
            topics=[topic], log_time_order=False
        ):
            encoding = _encoding(schema, channel)
            t_ns = int(message.log_time)
            data = message.data
            try:
                if encoding.lower() in {"json", "jsonschema"}:
                    payload = decode_json_bytes(data)
                    if not isinstance(payload, dict):
                        continue
                    fmt = str(payload.get("format") or "jpeg")
                    raw = payload.get("data") or b""
                    if isinstance(raw, str):
                        import base64

                        raw = base64.b64decode(raw)
                    yield t_ns, fmt, bytes(raw)
                else:
                    fmt, blob = decode_compressed_image_bytes(data)
                    yield t_ns, fmt or "jpeg", blob
            except Exception:
                continue
