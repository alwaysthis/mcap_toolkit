"""Background JPEG decode so playback never blocks the GUI thread."""

from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal


class FrameLoader(QThread):
    decoded = pyqtSignal(object, object, str, object)

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._job: tuple[str, str, int, int] | None = None
        self._stop = False

    def request(self, path: str, topic: str, t_ns: int, gen: int) -> None:
        with self._lock:
            self._job = (path, topic, int(t_ns), int(gen))

    def stop(self) -> None:
        self._stop = True
        with self._lock:
            self._job = None

    def run(self) -> None:
        from mcap.reader import SeekingReader
        from mcap_toolkit.image.decode import decode_compressed_image
        from mcap_toolkit.io.mcap_index import read_compressed_at

        handle = None
        reader = None
        cur_path: str | None = None
        while not self._stop:
            with self._lock:
                job = self._job
                self._job = None
            if job is None:
                self.msleep(8)
                continue
            path, topic, t_ns, gen = job
            with self._lock:
                newer = self._job
            if newer is not None:
                continue
            img = None
            try:
                if cur_path != path or reader is None:
                    if handle is not None:
                        try:
                            handle.close()
                        except Exception:
                            pass
                    handle = open(path, "rb")
                    reader = SeekingReader(handle, validate_crcs=False)
                    cur_path = path
                got = read_compressed_at(path, topic, t_ns, reader=reader)
                if got is None:
                    try:
                        handle.close()
                    except Exception:
                        pass
                    handle = open(path, "rb")
                    reader = SeekingReader(handle, validate_crcs=False)
                    got = read_compressed_at(path, topic, t_ns, reader=reader)
                if got is not None:
                    fmt, data = got
                    img = decode_compressed_image(data, fmt)
            except Exception:
                img = None
                reader = None
                if handle is not None:
                    try:
                        handle.close()
                    except Exception:
                        pass
                    handle = None
                cur_path = None
            if self._stop:
                break
            self.decoded.emit(img, t_ns, topic, gen)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
