"""Protobuf / JSON payload decode. No Qt."""

from __future__ import annotations

import json
from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct, Value

try:
    from foxglove_schemas_protobuf.CompressedImage_pb2 import CompressedImage
except ImportError:  # pragma: no cover
    CompressedImage = None  # type: ignore[misc, assignment]


def protobuf_value_to_python(value: Value) -> Any:
    kind = value.WhichOneof("kind")
    if kind == "null_value" or kind is None:
        return None
    if kind == "number_value":
        return value.number_value
    if kind == "string_value":
        return value.string_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "struct_value":
        return {k: protobuf_value_to_python(v) for k, v in value.struct_value.fields.items()}
    if kind == "list_value":
        return [protobuf_value_to_python(v) for v in value.list_value.values]
    return None


def struct_to_dict(msg: Struct) -> dict[str, Any]:
    return {k: protobuf_value_to_python(v) for k, v in msg.fields.items()}


def decode_struct_bytes(data: bytes) -> dict[str, Any]:
    msg = Struct()
    msg.ParseFromString(data)
    return struct_to_dict(msg)


def decode_struct_bytes_skip(data: bytes, skip: frozenset[str] | set[str]) -> dict[str, Any]:
    msg = Struct()
    msg.ParseFromString(data)
    return {k: protobuf_value_to_python(v) for k, v in msg.fields.items() if k not in skip}


def decode_compressed_image_bytes(data: bytes) -> tuple[str, bytes]:
    """Return (format, compressed_payload) from a foxglove.CompressedImage protobuf."""
    if CompressedImage is None:
        raise RuntimeError("foxglove-schemas-protobuf is required to decode CompressedImage")
    msg = CompressedImage()
    msg.ParseFromString(data)
    fmt = str(msg.format or "")
    payload = bytes(msg.data)
    return fmt, payload


def decode_json_bytes(data: bytes) -> Any:
    text = data.decode("utf-8")
    return json.loads(text)


def schema_looks_like_image(schema_name: str, topic: str) -> bool:
    name = (schema_name or "").lower()
    t = (topic or "").lower()
    if "compressedimage" in name.replace("_", "").replace(".", ""):
        return True
    if "compressedimage" in name:
        return True
    if t.startswith("image/"):
        return True
    return False


def schema_looks_like_struct(schema_name: str) -> bool:
    name = (schema_name or "").lower()
    return "struct" in name or name.endswith("json")


def message_to_plain(data: bytes, *, encoding: str, schema_name: str) -> Any:
    enc = (encoding or "").lower()
    if enc in {"json", "jsonschema"}:
        return decode_json_bytes(data)
    if schema_looks_like_image(schema_name, ""):
        return decode_compressed_image_bytes(data)
    if "struct" in (schema_name or "").lower() or enc in {"protobuf", "proto", ""}:
        try:
            return decode_struct_bytes(data)
        except Exception:
            if enc in {"json", "jsonschema"}:
                raise
            try:
                return decode_json_bytes(data)
            except Exception:
                return MessageToDict(Struct())
    return decode_json_bytes(data)
