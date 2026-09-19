"""Panel ids and titles. Workspace tabs replaced tiled docks."""

from __future__ import annotations

DOCK_IMAGE = "dock_image"
DOCK_ROI = "dock_roi"
DOCK_TEMPERATURE = "dock_temperature"
DOCK_SHUTTER = "dock_shutter"

DOCK_ORDER: tuple[str, ...] = (
    DOCK_IMAGE,
    DOCK_ROI,
    DOCK_TEMPERATURE,
    DOCK_SHUTTER,
)

SETTINGS_ORG = "CLC"
SETTINGS_APP = "mcap_toolkit"


def dock_titles() -> dict[str, str]:
    return {
        DOCK_IMAGE: "Image",
        DOCK_ROI: "ROI Intensity",
        DOCK_TEMPERATURE: "T (°C)",
        DOCK_SHUTTER: "Shutter Status",
    }
