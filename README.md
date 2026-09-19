# mcap_toolkit

Standalone PyQt6 viewer/exporter for CLC-MBE `.mcap` recordings. Open a file (drag-and-drop or **文件 → 打开**), inspect images and time series, play back, and export PNG / CSV / screenshots / video.

This is a **viewer only**: no camera, OPC, or recording. It does not modify `clc_mbe`.

## Run

Requires [uv](https://docs.astral.sh/uv/).

```bat
run.bat
```

Or:

```bat
uv sync
uv run python -m mcap_toolkit
uv run python -m mcap_toolkit path\to\file.mcap
```

Tests:

```bat
uv sync --extra dev
uv run pytest
```

Video export uses **ffmpeg** when it is on `PATH`. If it is missing, the app falls back to **OpenCV** (already installed with the toolkit) and still writes MP4.

## Workspace (VS Code–like)

The window chrome follows **VS Code Dark+**. Until a file is opened the editor area is **blank**. After open there are two groups, each with tabs (one figure per tab, not tiled plots):

| Panel id | Title | Default group |
|---|---|---|
| `dock_image` | 图像 | left |
| `dock_roi` | ROI Intensity | right |
| `dock_temperature` | T (°C) | right |
| `dock_shutter` | Shutter Status | right |

Close a tab with its ×. Re-open from **视图**. **视图 → 恢复默认布局** restores the split above. The seek bar is full width; playback icons sit under it.

Plots use a MATLAB-style white figure (box, ColorOrder, grid). Geometry is stored in `QSettings` (org `CLC`, app `mcap_toolkit`).

Opening is two-pass like Foxglove Studio: message indexes first (timeline + image timestamps), then plot topics only. JPEG is decoded on seek using a kept-open reader. `stage/image_params` is not decoded on open.

## Image panel

- Channel combo and ROI flags sit **under** the image.
- Channel combo: `image/gray` → **灰度**, `image/output` → **最终图**, plus any other image topics in the file (raw topic in the tooltip).
- **预览加上 ROI框** overlays ROI on the on-screen preview only.
- **保存加上 ROI框** overlays ROI on screenshot and video only. The two flags are independent.
- Right-click: **截图** (PNG of the current frame), **导出视频** (selected channel over the file timeline).

ROI geometry comes from `stage/roi_intensity.rois`. If that list is missing, no boxes are drawn (intensities are not used to guess boxes).

## Plot panels

| Panel | Y label | Source |
|---|---|---|
| ROI | ROI Intensity | `stage/roi_intensity` `roi_1..N` |
| Temperature | T (°C) | `stage/mbe/furnace/<name>` field `pv` |
| Shutter/MFC | Shutter Status | shutters `0/1/2`; `mfc_o2` / `mfc_n2` `valve_state_4` |

The transport bar sets the time scale globally (default **相对时间**):

- **相对时间**: seconds from the first message, X starts at 0, label **Time (sec.)**
- **绝对时间**: local wall-clock **时:分:秒**, label **Time**

Shutters and valves are drawn as discrete steps.

Each plot: icon tools for box-zoom / pan / reset; drag the figure frame to resize. Legend collapses to a side rail. Right-click **导出 PNG / CSV**. CSV is full resolution of the visible X range; the on-screen curve may be downsampled.

## MCAP topic map (CLC-MBE, 2026-09-17+)

| Topic | Schema / payload |
|---|---|
| `image/gray` | `foxglove.CompressedImage` JPEG, single-channel intensity |
| `image/output` | `foxglove.CompressedImage` JPEG, HSV-baked BGR |
| `stage/image_params` | optional; missing on older files |
| `stage/roi_intensity` | Struct: `roi_count`, `roi_1..N`, optional `rois[]` `{x,y,width,height,shape}` |
| `stage/mbe/furnace/<name>` | Struct: `pv` (°C). Names include srtop, srbottom, batop, babottom, ti, la, nd, ni, channel10, t2750, sh600sic |
| `stage/mbe/shutters` | Struct ints: main, sr, plasma, ba, nd, ti, ni, channel10, la (`0` closed, `1` open, `2` intermediate/fault) |
| `stage/mbe/mfc_o2`, `stage/mbe/mfc_n2` | Struct including `valve_state_4` (`0`/`1`) |

Older files may use PNG for `image/output`, omit gray/params, or omit HSV baking. They still open; missing channels are hidden.

The viewer does not include a pressure plot.

## Layout of this repo

Root stays small: `run.bat`, `pyproject.toml`, `uv.lock`, docs. Code lives under `src/mcap_toolkit/`:

- `io/` — MCAP index and decode (no Qt)
- `playback/` — playhead clock
- `image/` — JPEG/PNG decode and ROI overlay (shared by preview and export)
- `plot/` — series models and time axis
- `export/` — PNG / CSV / ffmpeg video
- `layout/` — factory dock layout and `QMainWindow` save/restore
- `ui/` — window, docks, menus, transport
