## 0.1.22 — 2026-09-18

- Window and taskbar use an app icon (dark tile, play + trace) that matches the UI chrome.

## 0.1.21 — 2026-09-18

- UI language is English (menus, dialogs, tooltips, status). Behavior is unchanged.

## 0.1.20 — 2026-09-18

- Video export no longer requires a separate ffmpeg install. If `ffmpeg` is not on PATH, OpenCV writes the MP4.

## 0.1.19 — 2026-09-18

- Transport row: current time on the left, prev / play / next centered, speed and time-mode on the right.

## 0.1.18 — 2026-09-18

- Close `×` is a light glyph, inset from the tab edge so it no longer sits on the border.
- The blue underline under the tab strip is gone. The active tab uses the same `#2d2d30` as the pane, darker than the surrounding chrome.

## 0.1.17 — 2026-09-18

- Tabs are rounded on top only (square bottom), with a close `×` and no `+`. Dark chrome and the blue underline are unchanged.

## 0.1.16 — 2026-09-18

- Tabs keep the browser-chip layout (icon, title, close, plus) but use the app’s dark chrome. Selected tab is a lighter gray pill; a 2 px accent line under the tab strip uses the same blue as the rest of the UI.
- Each pane has a `+` to reopen closed tabs (menu if more than one is available).

## 0.1.15 — 2026-09-18

- Tabs are rounded pills with an icon and close button (selected tab is light, like a browser chip).
- Opening a file shows a wait message and progress bar on the blank workspace until the index is ready.
- Status bar uses the same gray chrome as the rest of the window (no blue bar).

## 0.1.14 — 2026-09-18

- Transport buttons match a media-player layout: skip-prev / circular play-pause / skip-next, drawn as gray icons without boxed glyphs.
- Seek-bar remaining track is a lighter gray (`#9a9aa3`) so it no longer disappears into the transport background; the played range stays bright blue.

## 0.1.13 — 2026-09-18

- Plot grid is a ViewBox item (under the traces and playhead), so scrubbing the seek bar no longer wipes grid lines.
- Axis tick numbers are shown again: Y values, relative X in seconds, absolute X as local `HH:MM:SS`.

## 0.1.12 — 2026-09-18

- Legend is built from topic names and known fields as soon as the file is indexed (ROI count from the first ROI message). No waiting for the whole decode.
- The open worker keeps full-resolution samples for CSV. The GUI only receives about 2000 display points per series and appends them into reserved numpy buffers.
- Opening a file no longer sorts all samples or rebuilds `build_plot_bundle` on the UI thread.

## 0.1.11 — 2026-09-18

- Opening a file shows the image first, then plot tabs. The decoder yields ~24 visual batches with backpressure; the UI appends one batch every 33 ms so traces and legend items grow instead of popping in after a hitch.
- Plot series are streamed from decoded points (no full sort + rebuild while loading). The legend list only appends new keys.
- Frame decode thread starts after the window is shown, so launching the app is lighter.

## 0.1.10 — 2026-09-18

- Plot decode no longer sleeps between batches. The worker fills a queue as fast as it can; the UI drains it at 20 Hz so traces still grow, but loading is limited by file decode instead of a 40 ms delay.

## 0.1.9 — 2026-09-18

- Plot loading is paced (small batches + 40 ms yield) so traces grow on screen instead of appearing all at once after decode finishes.
- Playback, seeking, and channel switching stay usable while curves stream in; the GUI only appends samples on the load thread handshake and redraws on a 10 Hz timer.

## 0.1.8 — 2026-09-18

- Open is Foxglove-style again: the image appears as soon as the file is indexed. Plot traces stream in while struct messages decode (batches ~400, UI refresh ~12 Hz).

## 0.1.7 — 2026-09-18

- Opening a file waits until samples are decoded, then shows the workspace with curves already drawn (layout first, then plot, then fit). No more empty chart tabs while loading.
- App-wide QSS no longer styles `QGraphicsView` (that was hiding pyqtgraph traces).

## 0.1.6 — 2026-09-18

- Plot series are built on the GUI thread after samples are in `recording` (no numpy bundle through a queued Qt signal). Chart tabs are added only once the curves exist.
- View range uses the data min/max (not pyqtgraph auto-range on a zero-size widget). Plots refit on first real resize.
- Topic names match with or without a leading `/`. Empty SeekingReader topic filters fall back to a linear scan.

## 0.1.5 — 2026-09-18

- RHEED/raw frames are fetched at the indexed timestamp at-or-before the playhead (not a ±5 ms window around a continuous clock), so the picture advances while playing or scrubbing.
- Decoded frames are shown even if a newer request is already in flight (no longer dropped as “stale”).
- Plot curves are drawn again after the tab layout has a real size, so opening a file fills ROI / T / Shutter instead of leaving empty axes.

## 0.1.4 — 2026-09-18

- Nanosecond timestamps are no longer sent through `pyqtSignal(int)` (Windows truncates that to 32-bit, which made the status time negative, froze the seek bar, and made the plot playhead race). Slots read `clock.playhead_ns` as a Python int.

## 0.1.3 — 2026-09-18

- Playback clock uses `time.perf_counter_ns()` (no Qt millisecond/nanosecond mix-up).
- JPEG decode runs on a background thread so the seek bar and plot playhead can move at 30 Hz.
- Zero timestamps are ignored when computing the file span (a 0 sample no longer stretches the axis to decades or makes the playhead race).
- Play never jumps back to t0; the bar, RHEED image, and plot line share one playhead.

## 0.1.2 — 2026-09-18

- One time base for clock, seek bar, plots, and image. Play continues from the bar (does not jump to t0). The bar follows the clock; RHEED updates on the same playhead. Plot playhead is seconds-from-t0 (integer ns subtract), so the line sweeps the traces once instead of racing/looping.
- Play reads the visible seek-bar ratio first (not a cached ns that could have been reset to t0).
- Dragging the bar updates plots and the image from the same ratio; the clock is not used as the time source for scrubbing.
- `set_time_label` only changes the time text. Completing a file load keeps an already-moved seek bar.

## 0.1.1 — 2026-09-18

- Plot styling: figure/box/tick pens 1 px, grid 0.5 px, curves 2 px; tick numbers hidden.
- Legend sits at the top of the rail (not full plot height). Image channel combo is compact.
- Seek bar keeps its position while dragging (no snap-back from plot playhead or load-complete `set_range`). Transport time uses integer ns mapping: relative seconds from t0, absolute local `HH:MM:SS`.
- Transport seek no longer grabs the mouse (Windows was eating later clicks). Play / prev / next are real push buttons and re-sync the file time range before acting.
- Clicking play/prev/next no longer maps onto the seek bar or resets the playhead to t0. Scrubbing decodes the image on the drag path (Qt timers do not fire while the mouse is held).
- Image channels: default **RHEED image** (`image/output`); grayscale is **raw image** (`image/gray`).
- Transport uses a fully styled QSlider. Drag writes the clock immediately (so buttons keep that time) and decodes the current image on the same path.
- Play continues from the current slider position; it no longer jumps back to the start of the file.

## 0.1.0 — 2026-09-17

- Initial CLC-MBE MCAP viewer/exporter: drag-drop and File→Open, PNG/CSV/screenshot/video export.
- VS Code–inspired chrome with visible separators (menu / workspace / transport; tabs contrast with the pane). Default split is 图像 | ROI / T / Shutter.
- MATLAB-style plots: thicker axes/ticks, gray sparse grid, drag the figure border to resize (double-click to refit). Icon tools: box-zoom, pan, reset. Legend collapses to a side rail. PNG/CSV export is right-click only.
- Transport: taller bar, full-width custom seek (live image + playhead while dragging), centered prev / play-pause toggle / next.
- Image channel combo sits under the picture.
- Open path follows Foxglove: index timestamps from MCAP summary first, then decode only plot topics (skip JPEG and per-frame `image_params`).
- Time scale: **相对时间** (default) is seconds from t0 (`Time (sec.)`); **绝对时间** is local clock `HH:MM:SS`. Plot X is always seconds from the first message.
