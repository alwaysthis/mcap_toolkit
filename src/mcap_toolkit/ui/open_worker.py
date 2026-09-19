"""Background MCAP open so the UI stays responsive."""

from __future__ import annotations

import queue

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from mcap_toolkit.plot.store import PlotStore


class OpenWorker(QObject):
    indexed = pyqtSignal(object)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path
        self.rec = None
        self.store = PlotStore()
        self.batches: queue.Queue = queue.Queue()

    def run(self) -> None:
        try:
            from mcap_toolkit.io.mcap_index import index_recording, iter_struct_batches

            rec = index_recording(self._path)
            self.rec = rec
            self.store = PlotStore(
                struct_counts=rec.struct_counts,
                roi_geoms=rec.roi_geoms,
            )
            self.indexed.emit(rec)
            already = rec.samples_by_topic
            if already:
                n = 0
                for topic, items in already.items():
                    for sample in items:
                        self.store.ingest(topic, sample, capture_geom=not rec.roi_geoms)
                        n += 1
                        if n % 400 == 0:
                            delta = self.store.take_display()
                            if delta:
                                while self.batches.qsize() >= 2:
                                    QThread.msleep(8)
                                self.batches.put((delta, self.store.n_messages))
                rec.samples_by_topic = {}
            else:
                warnings: list[str] = []
                n = int(getattr(rec, "struct_count", 0) or 0)
                batch_size = max(200, min(4000, n // 24 if n else 800))
                for batch in iter_struct_batches(
                    rec.path, list(rec.plot_topics), batch_size=batch_size, warnings=warnings
                ):
                    for topic, items in batch.items():
                        for sample in items:
                            self.store.ingest(topic, sample, capture_geom=True)
                    delta = self.store.take_display()
                    if delta:
                        while self.batches.qsize() >= 2:
                            QThread.msleep(8)
                        self.batches.put((delta, self.store.n_messages))
                rec.warnings.extend(warnings)
            self.store.finish()
            delta = self.store.take_display()
            if delta:
                while self.batches.qsize() >= 2:
                    QThread.msleep(8)
                self.batches.put((delta, self.store.n_messages))
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
