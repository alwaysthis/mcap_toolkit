"""Write a numpy image (gray or BGR) to PNG."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def write_array_png(path: str | Path, image: np.ndarray) -> None:
    path = Path(path)
    if image.ndim == 2:
        pil = Image.fromarray(image, mode="L")
    elif image.ndim == 3 and image.shape[2] == 3:
        rgb = image[:, :, ::-1].copy()
        pil = Image.fromarray(rgb, mode="RGB")
    elif image.ndim == 3 and image.shape[2] == 4:
        rgba = image[:, :, [2, 1, 0, 3]].copy()
        pil = Image.fromarray(rgba, mode="RGBA")
    else:
        raise ValueError(f"unsupported image shape: {image.shape}")
    pil.save(path, format="PNG")
