"""Main window: VS Code two-pane tabs, transport, session wiring."""

from __future__ import annotations

from pathlib import Path
from queue import Empty

from PyQt6.QtCore import QSettings, QThread, Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from mcap_toolkit.export.csv_export import write_series_csv
from mcap_toolkit.export.png_export import write_array_png
from mcap_toolkit.export.video_export import write_video
from mcap_toolkit.image.decode import decode_compressed_image
from mcap_toolkit.image.overlay import render_rois_on_image
from mcap_toolkit.io.mcap_index import iter_compressed_topic
from mcap_toolkit.io.recording import Recording, frame_at_or_before, next_frame_time, prev_frame_time
from mcap_toolkit.layout.docks import (
    DOCK_IMAGE,
    DOCK_ORDER,
    DOCK_ROI,
    DOCK_SHUTTER,
    DOCK_TEMPERATURE,
    SETTINGS_APP,
    SETTINGS_ORG,
    dock_titles,
)
from mcap_toolkit.layout.workspace import Workspace
from mcap_toolkit.playback.clock import PlaybackClock
from mcap_toolkit.playback.frame_loader import FrameLoader
from mcap_toolkit.plot.models import bundle_from_metas, skeleton_metas
from mcap_toolkit.plot.time_axis import playhead_ns_from_ratio, ratio_from_playhead
from mcap_toolkit.ui.image_panel import ImagePanel
from mcap_toolkit.ui.open_worker import OpenWorker
from mcap_toolkit.ui.plot_panel import PlotPanel
from mcap_toolkit.ui.transport_bar import TransportBar

RECENT_MAX = 10


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MCAP Toolkit")
        self.resize(1400, 860)
        self.setAcceptDrops(True)

        self._recording: Recording | None = None
        self._bundle = None
        self._plot_store = None
        self._exporting = False
        self._load_thread: QThread | None = None
        self._plots_loading = False
        self._plots_dirty = False
        self._load_decode_done = False
        self._pending_plot_tabs = False
        self._plot_flush = QTimer(self)
        self._plot_flush.setInterval(33)
        self._plot_flush.timeout.connect(self._flush_plot_samples)
        self._clock = PlaybackClock(self)
        self._pending_image_ns: int | None = None
        self._last_image_flush = 0.0
        self._img_gen = 0
        self._shown_img_gen = 0
        self._req_frame_key: tuple[str, int] | None = None
        self._loader = FrameLoader()
        self._loader.decoded.connect(self._on_decoded_frame)
        QTimer.singleShot(0, self._loader.start)

        self._image = ImagePanel()
        self._plots: dict[str, PlotPanel] = {
            DOCK_ROI: PlotPanel(),
            DOCK_TEMPERATURE: PlotPanel(),
            DOCK_SHUTTER: PlotPanel(),
        }

        self._workspace = Workspace()
        self._workspace.set_panels(
            {
                DOCK_IMAGE: self._image,
                DOCK_ROI: self._plots[DOCK_ROI],
                DOCK_TEMPERATURE: self._plots[DOCK_TEMPERATURE],
                DOCK_SHUTTER: self._plots[DOCK_SHUTTER],
            }
        )

        self._transport = TransportBar()
        self._transport.setObjectName("transportBar")
        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._workspace, 1)
        column.addWidget(self._transport, 0)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self._build_menus()
        self._wire()
        QTimer.singleShot(0, self._restore_settings)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        act_open = QAction("&Open…", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._choose_open)
        file_menu.addAction(act_open)

        self._recent_menu = file_menu.addMenu("Open &Recent")
        file_menu.addSeparator()
        act_quit = QAction("E&xit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = self.menuBar().addMenu("&View")
        self._dock_actions: dict[str, QAction] = {}
        titles = dock_titles()
        for key in DOCK_ORDER:
            act = QAction(titles[key], self)
            act.setCheckable(True)
            act.setChecked(False)
            act.toggled.connect(lambda checked, k=key: self._toggle_panel(k, checked))
            view_menu.addAction(act)
            self._dock_actions[key] = act

        view_menu.addSeparator()
        act_factory = QAction("&Restore Default Layout", self)
        act_factory.triggered.connect(self._restore_factory)
        view_menu.addAction(act_factory)

        help_menu = self.menuBar().addMenu("&Help")
        act_about = QAction("&About", self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)
        self._rebuild_recent_menu()

    def _wire(self) -> None:
        clock = self._clock
        tr = self._transport
        tr.play_toggled.connect(self._toggle_play)
        tr.step_prev.connect(self._step_prev)
        tr.step_next.connect(self._step_next)
        tr.speed_changed.connect(clock.set_speed)
        tr.seek_ratio.connect(self._seek_ratio)
        tr.scrubbing_changed.connect(self._on_scrubbing)
        tr.time_mode_changed.connect(self._set_time_mode)
        clock.playhead_changed.connect(self._on_playhead)
        clock.playing_changed.connect(tr.set_playing)
        self._image.request_screenshot.connect(self._screenshot)
        self._image.request_video.connect(self._export_video)
        self._image.channel.currentIndexChanged.connect(lambda _i: self._on_image_channel())
        self._workspace.tab_closed.connect(self._on_tab_closed)
        for panel in self._plots.values():
            panel.export_png.connect(lambda p=panel: self._export_plot_png(p))
            panel.export_csv.connect(lambda p=panel: self._export_plot_csv(p))

    def _toggle_panel(self, key: str, checked: bool) -> None:
        if self._recording is None:
            act = self._dock_actions.get(key)
            if act is not None:
                act.blockSignals(True)
                act.setChecked(False)
                act.blockSignals(False)
            return
        if checked:
            self._workspace.show_panel(key)
        else:
            self._workspace.hide_panel(key)

    def _on_tab_closed(self, key: str) -> None:
        act = self._dock_actions.get(key)
        if act is None:
            return
        act.blockSignals(True)
        act.setChecked(False)
        act.blockSignals(False)

    def _sync_view_actions(self) -> None:
        for key, act in self._dock_actions.items():
            act.blockSignals(True)
            act.setChecked(self._recording is not None and self._workspace.has_panel(key))
            act.blockSignals(False)

    def _restore_factory(self) -> None:
        if self._recording is None:
            self._workspace.clear_file()
            self._sync_view_actions()
            return
        self._workspace.apply_factory()
        self._sync_view_actions()

    def _about(self) -> None:
        QMessageBox.information(
            self,
            "About",
            "MCAP Toolkit 0.1.22\nCLC-MBE recording viewer / exporter.\nViewer only — no acquisition.",
        )

    def _settings(self) -> QSettings:
        return QSettings(SETTINGS_ORG, SETTINGS_APP)

    def _restore_settings(self) -> None:
        s = self._settings()
        geo = s.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        split = s.value("splitter")
        if split is not None:
            self._workspace.splitter.restoreState(split)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        s = self._settings()
        s.setValue("geometry", self.saveGeometry())
        s.setValue("splitter", self._workspace.splitter.saveState())
        if self._recording is not None:
            self._recording.close_reader()
        self._loader.stop()
        self._loader.wait(1500)
        super().closeEvent(event)

    def _recent_paths(self) -> list[str]:
        raw = self._settings().value("recent") or []
        if isinstance(raw, str):
            raw = [raw]
        return [str(p) for p in raw if p]

    def _push_recent(self, path: str) -> None:
        items = [path, *[p for p in self._recent_paths() if p != path]][:RECENT_MAX]
        self._settings().setValue("recent", items)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        paths = self._recent_paths()
        if not paths:
            act = QAction("(empty)", self)
            act.setEnabled(False)
            self._recent_menu.addAction(act)
            return
        for p in paths:
            act = QAction(p, self)
            act.triggered.connect(lambda _=False, path=p: self.open_path(path))
            self._recent_menu.addAction(act)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".mcap"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".mcap"):
                self.open_path(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def _choose_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open MCAP", "", "MCAP (*.mcap);;All (*.*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if self._exporting:
            if (
                QMessageBox.question(self, "Export in progress", "Export is not finished. Open a new file anyway?")
                != QMessageBox.StandardButton.Yes
            ):
                return
        if self._load_thread is not None and self._load_thread.isRunning():
            QMessageBox.information(self, "Opening", "Wait until the current file finishes loading.")
            return
        p = Path(path)
        if not p.is_file():
            QMessageBox.warning(self, "Cannot open", f"File not found: {path}")
            return
        self.statusBar().showMessage(f"Opening {p.name}…")
        self._workspace.show_loading(f"Opening {p.name}…")
        worker = OpenWorker(str(p))
        thread = QThread(self)
        self._load_thread = thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.indexed.connect(self._on_indexed, Qt.ConnectionType.QueuedConnection)
        worker.finished_ok.connect(self._on_curves_done, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._on_load_failed, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.start()
        self._open_worker = worker

    def _on_indexed(self, rec: Recording) -> None:
        try:
            if self._recording is not None and self._recording is not rec:
                self._recording.close_reader()
            self._recording = rec
            worker = getattr(self, "_open_worker", None)
            self._plot_store = getattr(worker, "store", None)
            self._bundle = None
            self._req_frame_key = None
            self._shown_img_gen = 0
            self._plots_loading = True
            self._plots_dirty = False
            self._load_decode_done = False
            self._pending_plot_tabs = True
            self._plot_flush.stop()
            self._clock.set_range(rec.t0_ns, rec.t1_ns, reset=True)
            self._transport.set_range(rec.t0_ns, rec.t1_ns)
            self._image.set_recording(rec, load_frame=False)
            self._workspace.clear_file()
            self._workspace.show_panel(DOCK_IMAGE, group=self._workspace.left)
            self._ensure_plot_tabs()
            self._transport.set_playhead(self._clock.playhead_ns)
            self._request_image(self._clock.playhead_ns, force=True)
            self._plot_flush.start()
            p = Path(rec.path)
            self.setWindowTitle(f"MCAP Toolkit — {p.name}")
            self.statusBar().showMessage(f"Opened {p.name}, loading traces…")
        except Exception as exc:
            if self._recording is not None:
                self._workspace.apply_factory()
            else:
                self._workspace.show_idle()
            QMessageBox.critical(self, "Display failed", str(exc))
            self.statusBar().showMessage(f"Display failed: {exc}")

    def _drain_one_batch(self) -> bool:
        worker = getattr(self, "_open_worker", None)
        if worker is None:
            return False
        q = getattr(worker, "batches", None)
        if q is None:
            return False
        try:
            payload = q.get_nowait()
        except Empty:
            return False
        chunks = payload
        n_msg = None
        if isinstance(payload, tuple) and len(payload) == 2:
            chunks, n_msg = payload
        if not chunks:
            return True
        by_kind: dict[str, list] = {"roi": [], "temperature": [], "shutter": []}
        for item in chunks:
            kind = item[0]
            if kind in by_kind:
                by_kind[kind].append(item)
        for kind, dock in (
            ("roi", DOCK_ROI),
            ("temperature", DOCK_TEMPERATURE),
            ("shutter", DOCK_SHUTTER),
        ):
            if by_kind[kind]:
                self._plots[dock].append_chunks(by_kind[kind], streaming=True)
        for panel in self._plots.values():
            panel.set_playhead(self._clock.playhead_ns)
        if not self._clock.playing and n_msg is not None:
            self.statusBar().showMessage(f"Plotting… decoded {n_msg} messages")
        return True

    def _ensure_plot_tabs(self) -> None:
        if not self._pending_plot_tabs:
            return
        rec = self._recording
        if rec is None:
            return
        self._pending_plot_tabs = False
        metas = skeleton_metas(list(rec.plot_topics), roi_count=int(rec.roi_count or 0))
        bundle = bundle_from_metas(metas, loading=True)
        self._bundle = bundle
        for key in (DOCK_ROI, DOCK_TEMPERATURE, DOCK_SHUTTER):
            self._workspace.show_panel(key, group=self._workspace.right)
        self._plots[DOCK_ROI].set_spec(bundle.roi, rec.t0_ns, rec.t1_ns)
        self._plots[DOCK_TEMPERATURE].set_spec(bundle.temperature, rec.t0_ns, rec.t1_ns)
        self._plots[DOCK_SHUTTER].set_spec(bundle.shutter, rec.t0_ns, rec.t1_ns)
        self._set_time_mode(self._transport.current_time_mode())
        self._sync_view_actions()

    def _flush_plot_samples(self) -> None:
        rec = self._recording
        if rec is None:
            return
        self._ensure_plot_tabs()
        got = self._drain_one_batch()
        if got:
            return
        if self._load_decode_done:
            self._finalize_plots()

    def _on_curves_done(self) -> None:
        rec = self._recording
        self._load_decode_done = True
        worker = getattr(self, "_open_worker", None)
        if worker is not None:
            self._plot_store = getattr(worker, "store", self._plot_store)
        if rec is not None:
            try:
                rec.open_reader()
            except Exception:
                pass
        self._flush_plot_samples()

    def _finalize_plots(self) -> None:
        if not self._plots_loading:
            return
        self._plots_loading = False
        self._plot_flush.stop()
        rec = self._recording
        if rec is not None:
            self._ensure_plot_tabs()
            for panel in self._plots.values():
                panel.finish_streaming()
                panel.set_playhead(self._clock.playhead_ns)
            if not self._clock.playing and not self._transport.is_dragging():
                for panel in self._plots.values():
                    panel.reset_view()
            self._apply_playhead(self._clock.playhead_ns, move_slider=not self._transport.is_dragging())
            p = Path(rec.path)
            self._push_recent(str(p))
            warn = "; ".join(rec.warnings[:4])
            n_img = sum(len(t.frames) for t in rec.image_topics)
            n_roi = len(self._plots[DOCK_ROI].spec().series)
            n_t = len(self._plots[DOCK_TEMPERATURE].spec().series)
            n_s = len(self._plots[DOCK_SHUTTER].spec().series)
            msg = (
                f"Opened {p.name}  ·  image frames {n_img}  · "
                f"traces ROI {n_roi} / T {n_t} / shutter {n_s}  · "
                f"duration {(rec.t1_ns - rec.t0_ns)/1e9:.1f}s"
            )
            if warn:
                msg += f"  · {warn}"
                QMessageBox.warning(self, "File warnings", "\n".join(rec.warnings[:12]))
            if not self._clock.playing:
                self.statusBar().showMessage(msg)
        if self._load_thread is not None:
            self._load_thread.quit()

    def _on_load_failed(self, message: str) -> None:
        self._plots_loading = False
        self._load_decode_done = False
        self._plot_flush.stop()
        if self._load_thread is not None:
            self._load_thread.quit()
        if self._recording is not None:
            self._workspace.apply_factory()
        else:
            self._workspace.show_idle()
        QMessageBox.critical(self, "Cannot open", message)
        self.statusBar().showMessage(f"Open failed: {message}")

    def _recording_span(self) -> tuple[int, int] | None:
        rec = self._recording
        if rec is None:
            return None
        t0, t1 = int(rec.t0_ns), int(rec.t1_ns)
        if t1 <= t0:
            times: list[int] = []
            for topic in rec.image_topics:
                times.extend(int(f.t_ns) for f in topic.frames)
            for samples in rec.samples_by_topic.values():
                if samples:
                    times.append(int(samples[0].t_ns))
                    times.append(int(samples[-1].t_ns))
            if times:
                t0, t1 = min(times), max(times)
                rec.t0_ns, rec.t1_ns = t0, t1
        if t1 <= t0:
            return None
        if self._clock.t0_ns != t0 or self._clock.t1_ns != t1:
            self._clock.set_range(t0, t1)
        self._transport.set_range(t0, t1)
        return t0, t1

    def _on_playhead(self) -> None:
        self._apply_playhead(self._clock.playhead_ns, move_slider=not self._transport.is_dragging())

    def _show_playhead(self, t_ns: int, *, move_slider: bool, eager_image: bool) -> None:
        self._apply_playhead(int(t_ns), move_slider=move_slider)

    def _apply_playhead(self, t_ns: int, *, move_slider: bool = True, eager_image: bool = False) -> None:
        t_ns = int(t_ns)
        t0, t1 = int(self._clock.t0_ns), int(self._clock.t1_ns)
        if t1 > t0:
            t_ns = min(max(t_ns, t0), t1)
        if move_slider:
            self._transport.set_playhead(t_ns)
        else:
            self._transport.set_time_label(t_ns)
        for panel in self._plots.values():
            try:
                panel.set_playhead(t_ns)
            except Exception:
                pass
        self._request_image(t_ns, force=eager_image)
        if self._clock.playing:
            t0, t1 = self._clock.t0_ns, self._clock.t1_ns
            span = t1 - t0
            if span > 0:
                rel = max(0.0, (int(t_ns) - t0) / 1e9)
                dur = span / 1e9
                self.statusBar().showMessage(f"Playing  {rel:.2f} / {dur:.1f} s")

    def _relayout_plots(self) -> None:
        for panel in self._plots.values():
            try:
                panel.relayout()
            except Exception:
                pass

    def _on_image_channel(self) -> None:
        self._req_frame_key = None
        if self._recording is None:
            return
        self._request_image(int(self._clock.playhead_ns), force=True)

    def _request_image(self, t_ns: int, *, force: bool = False) -> None:
        rec = self._recording
        topic = self._image.current_topic()
        if rec is None or topic is None:
            return
        index = rec.image_topic(topic)
        if index is None or not index.frames:
            return
        ref = frame_at_or_before(index.frames, int(t_ns))
        if ref is None:
            return
        key = (topic, int(ref.t_ns))
        if (not force) and key == self._req_frame_key:
            return
        self._req_frame_key = key
        self._img_gen += 1
        self._loader.request(rec.path, topic, int(ref.t_ns), self._img_gen)

    def _on_decoded_frame(self, image, t_ns, topic: str, gen) -> None:
        if image is None:
            return
        try:
            gen_i = int(gen)
        except (TypeError, ValueError):
            gen_i = 0
        if gen_i < self._shown_img_gen:
            return
        if topic != self._image.current_topic():
            return
        self._shown_img_gen = gen_i
        self._image.show_pixels(image, int(t_ns))

    def _toggle_play(self) -> None:
        if self._clock.playing:
            self._clock.pause()
            self.statusBar().showMessage("Paused")
            return
        self._transport.slider.cancel_drag()
        span = self._recording_span()
        if span is None:
            self.statusBar().showMessage("This file has no usable time range, so playback is unavailable.")
            return
        t0, t1 = span
        ratio = self._transport.slider_ratio()
        t_ns = playhead_ns_from_ratio(t0, t1, ratio)
        if t_ns >= t1:
            self.statusBar().showMessage("At the end of the file. Drag the seek bar, then play.")
            return
        if not self._clock.play(start_ns=t_ns):
            self.statusBar().showMessage("Cannot play.")
            return
        self._apply_playhead(t_ns, move_slider=True)

    def _on_scrubbing(self, on: bool) -> None:
        if on:
            if self._clock.playing:
                self._clock.pause()
                self.statusBar().showMessage("Paused")
            return
        self._request_image(int(self._clock.playhead_ns))

    def _seek_ratio(self, ratio: float) -> None:
        if self._clock.playing:
            self._clock.pause()
            self.statusBar().showMessage("Paused")
        span = self._recording_span()
        if span is None:
            return
        t0, t1 = span
        t_ns = playhead_ns_from_ratio(t0, t1, ratio)
        self._clock.seek(t_ns)
        self._apply_playhead(t_ns, move_slider=False)

    def _set_time_mode(self, mode: str) -> None:
        for panel in self._plots.values():
            panel.set_time_mode(mode)
        if self._recording is not None:
            self._transport.set_time_label(self._clock.playhead_ns)

    def _current_frames(self):
        rec = self._recording
        index = self._image.current_index()
        if rec is None or index is None:
            return []
        return index.frames

    def _step_next(self) -> None:
        if self._recording_span() is None:
            return
        frames = self._current_frames()
        nxt = next_frame_time(frames, self._clock.playhead_ns) if frames else None
        if nxt is None:
            nxt = min(self._clock.t1_ns, self._clock.playhead_ns + 1_000_000_000 // 30)
        self._clock.seek(nxt)
        self._apply_playhead(self._clock.playhead_ns, move_slider=True, eager_image=True)

    def _step_prev(self) -> None:
        if self._recording_span() is None:
            return
        frames = self._current_frames()
        prv = prev_frame_time(frames, self._clock.playhead_ns) if frames else None
        if prv is None:
            prv = max(self._clock.t0_ns, self._clock.playhead_ns - 1_000_000_000 // 30)
        self._clock.seek(prv)
        self._apply_playhead(self._clock.playhead_ns, move_slider=True, eager_image=True)

    def _screenshot(self) -> None:
        rec = self._recording
        if rec is None:
            return
        img = self._image.frame_pixels(
            overlay=self._image.save_overlay_enabled(),
            t_ns=self._clock.playhead_ns,
        )
        if img is None:
            QMessageBox.warning(self, "Screenshot", "There is no image to save.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save screenshot", "frame.png", "PNG (*.png)")
        if not path:
            return
        try:
            write_array_png(path, img)
            self.statusBar().showMessage(f"Saved screenshot {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Screenshot failed", str(exc))

    def _export_video(self) -> None:
        rec = self._recording
        index = self._image.current_index()
        if rec is None or index is None or not index.frames:
            QMessageBox.warning(self, "Export video", "No image channel to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export video", "export.mp4", "MP4 (*.mp4)")
        if not path:
            return
        overlay = self._image.save_overlay_enabled()
        dts = [
            (index.frames[i].t_ns - index.frames[i - 1].t_ns) / 1e9
            for i in range(1, len(index.frames))
        ]
        fps = 10.0
        if dts:
            med = sorted(dts)[len(dts) // 2]
            if med > 1e-6:
                fps = max(1.0, min(30.0, 1.0 / med))

        def frames_iter():
            for _t_ns, fmt, data in iter_compressed_topic(rec.path, index.topic):
                try:
                    pix = decode_compressed_image(data, fmt)
                except Exception:
                    continue
                if overlay:
                    rois = rec.rois_at(_t_ns)
                    if rois:
                        pix = render_rois_on_image(pix, rois)
                yield pix

        self._exporting = True
        progress = QProgressDialog("Exporting video…", "Cancel", 0, len(index.frames), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()
        QApplication.processEvents()
        cancelled = {"v": False}
        progress.canceled.connect(lambda: cancelled.update(v=True))

        def on_prog(n: int) -> None:
            progress.setValue(n)
            QApplication.processEvents()
            if cancelled["v"]:
                raise RuntimeError("cancelled")

        try:
            write_video(path, frames_iter(), fps=fps, progress=on_prog)
            self.statusBar().showMessage(f"Exported video {path}")
        except RuntimeError as exc:
            if "cancelled" in str(exc):
                self.statusBar().showMessage("Export cancelled")
            else:
                QMessageBox.critical(self, "Video export failed", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "Video export failed", str(exc))
        finally:
            self._exporting = False
            progress.close()

    def _export_plot_png(self, panel: PlotPanel) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", f"{panel.spec().kind}.png", "PNG (*.png)")
        if not path:
            return
        try:
            import pyqtgraph.exporters  # noqa: F401

            panel.grab_plot_png(path)
            self.statusBar().showMessage(f"Exported {path}")
        except Exception as exc:
            QMessageBox.critical(self, "PNG export failed", str(exc))

    def _export_plot_csv(self, panel: PlotPanel) -> None:
        rec = self._recording
        if rec is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"{panel.spec().kind}.csv", "CSV (*.csv)")
        if not path:
            return
        x0, x1 = panel.x_range_ns()
        store = self._plot_store
        spec = panel.spec()
        if store is not None:
            labels = {s.key: s.label for s in spec.series}
            visible = {s.key: s.visible for s in spec.series}
            series = store.series_for_csv([s.key for s in spec.series], labels=labels, visible=visible)
        else:
            series = spec.series
        try:
            write_series_csv(
                path,
                series,
                t0_ns=rec.t0_ns,
                x_min_ns=x0,
                x_max_ns=x1,
            )
            self.statusBar().showMessage(f"Exported {path}")
        except Exception as exc:
            QMessageBox.critical(self, "CSV export failed", str(exc))
