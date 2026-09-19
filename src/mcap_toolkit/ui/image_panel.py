"""Image dock: channel combo, independent preview/save ROI flags, screenshot/video."""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mcap_toolkit.image.decode import decode_compressed_image
from mcap_toolkit.image.overlay import render_rois_on_image
from mcap_toolkit.io.recording import ImageTopicIndex, Recording, frame_at_or_before
from mcap_toolkit.io.topics import TOPIC_OUTPUT, image_display_name


def bgr_or_gray_to_qimage(image: np.ndarray) -> QImage:
    if image.ndim == 2:
        h, w = image.shape
        bytes_per_line = w
        return QImage(
            np.ascontiguousarray(image).data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_Grayscale8,
        ).copy()
    rgb = np.ascontiguousarray(image[:, :, ::-1])
    h, w, _ = rgb.shape
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


class ImageCanvas(QWidget):
    context_export_video = pyqtSignal()
    context_screenshot = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.setMinimumSize(160, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def set_image(self, image: np.ndarray | None) -> None:
        if image is None or image.size == 0:
            self._pixmap = QPixmap()
            self.update()
            return
        self._pixmap = QPixmap.fromImage(bgr_or_gray_to_qimage(image))
        self.update()

    def _menu(self, pos) -> None:
        menu = QMenu(self)
        act_shot = menu.addAction("Screenshot")
        act_vid = menu.addAction("Export video")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is act_shot:
            self.context_screenshot.emit()
        elif chosen is act_vid:
            self.context_export_video.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._pixmap.isNull():
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No image")
            return
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


class ImagePanel(QWidget):
    request_screenshot = pyqtSignal()
    request_video = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._recording: Recording | None = None
        self._playhead_ns = 0
        self._shown_key: tuple[str, int, bool] | None = None

        self.channel = QComboBox()
        self.channel.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.channel.setMinimumContentsLength(6)
        self.channel.setMaximumWidth(160)
        self.channel.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.preview_roi = QCheckBox("ROI overlay (preview)")
        self.save_roi = QCheckBox("ROI overlay (export)")
        self.canvas = ImageCanvas()

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Channel"))
        bottom.addWidget(self.channel, 0)
        bottom.addStretch(1)
        bottom.addWidget(self.preview_roi)
        bottom.addWidget(self.save_roi)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(bottom)

        self.preview_roi.toggled.connect(lambda _v: self.refresh(force=True))
        self.canvas.context_screenshot.connect(self.request_screenshot)
        self.canvas.context_export_video.connect(self.request_video)

    def set_recording(self, recording: Recording | None, *, load_frame: bool = True) -> None:
        self._recording = recording
        self._shown_key = None
        self.channel.blockSignals(True)
        self.channel.clear()
        preferred = 0
        if recording is not None:
            for item in recording.image_topics:
                self.channel.addItem(item.display_name or image_display_name(item.topic), item.topic)
                idx = self.channel.count() - 1
                self.channel.setItemData(idx, item.topic, Qt.ItemDataRole.ToolTipRole)
                if item.topic == TOPIC_OUTPUT:
                    preferred = idx
            if self.channel.count():
                self.channel.setCurrentIndex(preferred)
        self.channel.blockSignals(False)
        if load_frame:
            self.refresh(force=True)
        else:
            self.canvas.set_image(None)

    def set_playhead(self, t_ns: int, *, force: bool = False) -> None:
        self._playhead_ns = int(t_ns)
        self.refresh(force=force)

    def show_pixels(self, image, t_ns: int) -> None:
        self._playhead_ns = int(t_ns)
        overlay = self.preview_roi.isChecked()
        if image is not None and overlay and self._recording is not None:
            rois = self._recording.rois_at(int(t_ns))
            if rois:
                try:
                    image = render_rois_on_image(image, rois)
                except Exception:
                    pass
        if image is None:
            return
        self.canvas.set_image(image)
        index = self.current_index()
        ref = frame_at_or_before(index.frames, self._playhead_ns) if index is not None else None
        self._shown_key = (index.topic if index else "", ref.t_ns if ref else -1, overlay)

    def current_topic(self) -> str | None:
        if self.channel.count() == 0:
            return None
        data = self.channel.currentData()
        return str(data) if data else None

    def current_index(self) -> ImageTopicIndex | None:
        if self._recording is None:
            return None
        topic = self.current_topic()
        if topic is None:
            return None
        return self._recording.image_topic(topic)

    def save_overlay_enabled(self) -> bool:
        return self.save_roi.isChecked()

    def preview_overlay_enabled(self) -> bool:
        return self.preview_roi.isChecked()

    def frame_pixels(self, *, overlay: bool, t_ns: int | None = None) -> np.ndarray | None:
        rec = self._recording
        index = self.current_index()
        if rec is None or index is None:
            return None
        t = rec.t0_ns if t_ns is None else int(t_ns)
        ref = frame_at_or_before(index.frames, t)
        if ref is None:
            return None
        payload = rec.fetch_compressed(index.topic, ref.t_ns)
        if payload is None:
            return None
        fmt, data = payload
        try:
            pixels = decode_compressed_image(data, fmt or ref.format)
        except Exception:
            return None
        if overlay:
            rois = rec.rois_at(ref.t_ns)
            if rois:
                return render_rois_on_image(pixels, rois)
        return pixels

    def refresh(self, *, force: bool = False) -> None:
        rec = self._recording
        if rec is None or not rec.image_topics:
            self.canvas.set_image(None)
            self._shown_key = None
            return
        index = self.current_index()
        overlay = self.preview_roi.isChecked()
        if index is not None:
            ref = frame_at_or_before(index.frames, self._playhead_ns)
            key = (index.topic, ref.t_ns if ref else -1, overlay)
            if (not force) and key == self._shown_key:
                return
        else:
            key = None
        try:
            img = self.frame_pixels(overlay=overlay, t_ns=self._playhead_ns)
        except Exception:
            img = None
        if img is None:
            return
        self.canvas.set_image(img)
        self._shown_key = key
