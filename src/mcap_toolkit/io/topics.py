"""Known CLC-MBE MCAP topics and display names. Qt-free."""

from __future__ import annotations

TOPIC_GRAY = "image/gray"
TOPIC_OUTPUT = "image/output"
TOPIC_IMAGE_PARAMS = "stage/image_params"
TOPIC_ROI = "stage/roi_intensity"
TOPIC_SHUTTERS = "stage/mbe/shutters"
TOPIC_MFC_O2 = "stage/mbe/mfc_o2"
TOPIC_MFC_N2 = "stage/mbe/mfc_n2"
FURNACE_PREFIX = "stage/mbe/furnace/"

IMAGE_DISPLAY_NAMES: dict[str, str] = {
    TOPIC_GRAY: "raw image",
    TOPIC_OUTPUT: "RHEED image",
}

SHUTTER_FIELDS: tuple[str, ...] = (
    "main",
    "sr",
    "plasma",
    "ba",
    "nd",
    "ti",
    "ni",
    "channel10",
    "la",
)

# Heuristic names for optional chamber pressure (often absent in 34-node recordings).
PRESSURE_KEY_HINTS: tuple[str, ...] = (
    "pressure",
    "press",
    "torr",
    "chamber_ig",
    "chamber_pg",
    "ig_pressure",
    "pg_pressure",
    "ion_gauge",
    "pirani",
    "igp",
    "p_chamber",
)


def image_display_name(topic: str) -> str:
    return IMAGE_DISPLAY_NAMES.get(topic, topic)


def image_topic_sort_key(topic: str) -> tuple[int, str]:
    if topic == TOPIC_OUTPUT:
        return (0, topic)
    if topic == TOPIC_GRAY:
        return (1, topic)
    return (2, topic)


def is_furnace_topic(topic: str) -> bool:
    return topic.startswith(FURNACE_PREFIX)


def furnace_name(topic: str) -> str:
    return topic[len(FURNACE_PREFIX) :] if is_furnace_topic(topic) else topic
