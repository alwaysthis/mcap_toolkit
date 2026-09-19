"""Playhead clock. No file-format details."""

from __future__ import annotations

import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal


class PlaybackClock(QObject):
    # No int payload: Windows Qt truncates ns timestamps to 32-bit.
    playhead_changed = pyqtSignal()
    playing_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._t0_ns = 0
        self._t1_ns = 0
        self._playhead_ns = 0
        self._speed = 1.0
        self._playing = False
        self._origin_ns = 0
        self._wall0_ns = 0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)

    @property
    def playhead_ns(self) -> int:
        return self._playhead_ns

    @property
    def t0_ns(self) -> int:
        return self._t0_ns

    @property
    def t1_ns(self) -> int:
        return self._t1_ns

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def playing(self) -> bool:
        return self._playing

    def set_range(self, t0_ns: int, t1_ns: int, *, reset: bool = False) -> None:
        self._t0_ns = int(t0_ns)
        self._t1_ns = max(int(t1_ns), self._t0_ns)
        if reset:
            self._playing = False
            self._timer.stop()
            self._playhead_ns = self._t0_ns
            return
        if self._t1_ns > self._t0_ns and self._playhead_ns > 0:
            self._playhead_ns = min(max(self._playhead_ns, self._t0_ns), self._t1_ns)

    def set_speed(self, speed: float) -> None:
        if self._playing:
            self._playhead_ns = self._now()
        self._speed = float(speed) if speed else 1.0
        if self._playing:
            self._arm()

    def set_playhead(self, t_ns: int, *, emit: bool = True) -> None:
        t = self._clamp(t_ns)
        if t is None:
            return
        changed = t != self._playhead_ns
        self._playhead_ns = t
        if emit and changed:
            self.playhead_changed.emit()

    def seek(self, t_ns: int, *, emit: bool = False) -> int:
        t = self._clamp(t_ns)
        if t is None:
            return self._playhead_ns
        self._playhead_ns = t
        if self._playing:
            self._arm()
        if emit:
            self.playhead_changed.emit()
        return t

    def play(self, start_ns: int | None = None) -> bool:
        if start_ns is not None:
            t = self._clamp(start_ns)
            if t is not None:
                self._playhead_ns = t
        if self._t1_ns <= self._t0_ns:
            self.pause()
            return False
        if self._playhead_ns >= self._t1_ns:
            self.pause()
            return False
        already = self._playing
        self._playing = True
        self._arm()
        if not already:
            self.playing_changed.emit(True)
        return True

    def pause(self) -> None:
        if self._playing:
            self._playhead_ns = self._now()
        self._timer.stop()
        if not self._playing:
            return
        self._playing = False
        self.playing_changed.emit(False)

    def stop(self) -> None:
        was = self._playing
        self._playing = False
        self._timer.stop()
        self._playhead_ns = self._t0_ns
        if was:
            self.playing_changed.emit(False)

    def toggle(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def _clamp(self, t_ns: int) -> int | None:
        try:
            t = int(t_ns)
        except (TypeError, OverflowError, ValueError):
            return None
        if self._t1_ns > self._t0_ns:
            t = min(max(t, self._t0_ns), self._t1_ns)
        return t

    def _now(self) -> int:
        if not self._playing or self._t1_ns <= self._t0_ns:
            return self._playhead_ns
        dt = time.perf_counter_ns() - self._wall0_ns
        nxt = self._origin_ns + int(dt * self._speed)
        return min(max(nxt, self._t0_ns), self._t1_ns)

    def _arm(self) -> None:
        self._origin_ns = self._playhead_ns
        self._wall0_ns = time.perf_counter_ns()
        self._timer.start()

    def _on_tick(self) -> None:
        if not self._playing:
            return
        nxt = self._now()
        self._playhead_ns = nxt
        self.playhead_changed.emit()
        if nxt >= self._t1_ns:
            self._playing = False
            self._timer.stop()
            self.playing_changed.emit(False)
