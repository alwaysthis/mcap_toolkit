"""JPEG/PNG CompressedImage decode."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from foxglove_schemas_protobuf.CompressedImage_pb2 import CompressedImage

from mcap_toolkit.image.decode import decode_compressed_image
from mcap_toolkit.io.decode import decode_compressed_image_bytes


def _jpeg_bytes(arr: np.ndarray) -> bytes:
    if arr.ndim == 2:
        pil = Image.fromarray(arr, mode="L")
    else:
        pil = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _png_bytes(arr: np.ndarray) -> bytes:
    pil = Image.fromarray(arr, mode="L" if arr.ndim == 2 else "RGB")
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def test_decode_jpeg_gray() -> None:
    src = np.arange(64, dtype=np.uint8).reshape(8, 8)
    blob = _jpeg_bytes(src)
    out = decode_compressed_image(blob, "jpeg")
    assert out.ndim in {2, 3}
    assert out.shape[0] == 8 and out.shape[1] == 8
    assert out.dtype == np.uint8


def test_decode_png() -> None:
    src = np.full((6, 7), 90, dtype=np.uint8)
    blob = _png_bytes(src)
    out = decode_compressed_image(blob, "png")
    assert out.shape[0] == 6 and out.shape[1] == 7
    if out.ndim == 2:
        assert int(out.mean()) == 90


def test_protobuf_compressed_image_roundtrip() -> None:
    src = np.zeros((4, 5), dtype=np.uint8)
    src[1, 2] = 200
    blob = _png_bytes(src)
    msg = CompressedImage()
    msg.format = "png"
    msg.data = blob
    fmt, data = decode_compressed_image_bytes(msg.SerializeToString())
    assert fmt == "png"
    decoded = decode_compressed_image(data, fmt)
    assert decoded.shape[0] == 4 and decoded.shape[1] == 5
