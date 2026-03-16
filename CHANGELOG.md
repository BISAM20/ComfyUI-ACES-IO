# Changelog

All notable changes to ComfyUI-ACES-IO are documented here.

---

## [1.3.7] — 2026-03-16

### Fixed
- **ProRes MOV export crash**: `fps` is now wrapped in `Fraction` before being passed to PyAV's `add_stream(rate=...)`. PyAV's `to_avrational()` requires an object with a `.numerator` attribute (int or Fraction) — passing a plain float caused `AttributeError: 'float' object has no attribute 'numerator'`.

---

## [1.3.6] — 2026-03-16

### Changed
- **README**: Updated documentation to cover all v1.3.x additions — OCIODisplay node, EXR color transforms, ProRes MOV export, ACES 1.2 auto-download, and Video Loader. Added dedicated sections for Display Transform, EXR Loader/Saver color transform inputs, and expanded Video Saver format table.
- **CHANGELOG**: Back-filled entries for v1.3.0 through v1.3.4.

---

## [1.3.5] — 2026-03-16

### Added
- **ACES IO — Display Transform (OCIODisplay)**: New node mirroring Nuke's `OCIODisplay` node. Applies a Display View Transform (input colorspace → display + view pipeline) and bakes the result into image data — unlike the Viewer node which is preview-only. Includes an **Invert** boolean to reverse the transform direction (display-referred → scene-referred), matching Nuke's `invert` knob exactly.

---

## [1.3.4] — 2026-03-15

### Changed
- **EXR Saver** — added optional `ocio_config` input, `input_transform`, and `colorspace` knobs. Converts `input_transform → colorspace` before writing, mirroring Nuke's Write node. Conversion is skipped when `ocio_config` is disconnected.
- **EXR Loader** — added optional `ocio_config` input, `colorspace`, and `output_transform` knobs. Converts `colorspace → output_transform` after loading, mirroring Nuke's Read node. Conversion is skipped when `ocio_config` is disconnected.

---

## [1.3.3] — 2026-03-15

### Changed
- Version bump (`pyproject.toml`).

---

## [1.3.2] — 2026-03-15

### Changed
- **ACES 1.2 always in dropdown**: `ACES 1.2` is now a permanent entry in `BUILTIN_CONFIGS` alongside ACES 1.3/2.0 — no longer conditionally injected only when the file already exists.
- **Auto-download on first use**: `load_config()` now triggers the ACES 1.2 download automatically when the config file is missing, then loads it immediately — no manual path required.
- Renamed preset label `"Custom path (ACES 1.2 / other)"` → `"Custom path (other)"` since ACES 1.2 has its own dedicated entry.

---

## [1.3.1] — 2026-03-15

### Changed
- Version bump (`pyproject.toml`).

---

## [1.3.0] — 2026-03-15

### Added
- **ProRes MOV export**: Video Saver now supports MOV ProRes 422, ProRes 422 HQ, ProRes 4444, and ProRes 4444 XQ formats via PyAV (`prores_ks` encoder; 10-bit YUV 4:2:2 / 4:4:4; alpha channel preserved for 4444 variants when input has 4 channels).

### Fixed
- **ACES 1.2 auto-download not running on fresh installs**: `download_aces12()` and `_refresh_aces12()` are now called from `__init__.py` at startup so the config is fetched before the first node execution.
- **`BUILTIN_CONFIG_KEYS` stale-reference bug**: The list is now mutated in-place in `_refresh_aces12()` so `nodes.py`'s imported binding always reflects updated keys.

---

## [1.2.0] — 2026-03-11

### Added
- **ACES IO — Video Loader**: New node for loading `.mov`, `.mp4`, `.mxf` and other video formats. Full Apple ProRes (4444, 422, LT, Proxy) support via PyAV. Outputs `IMAGE` tensor with frame range selection.
- **PNG / JPEG / TIFF support in EXR Loader**: The EXR Loader node now accepts `.png`, `.jpg`, `.jpeg`, `.tiff` in addition to `.exr` sequences.
- **ACES 1.2 auto-install**: `install.py` now automatically downloads the ACES 1.2 OpenColorIO config (~130 MB) during node installation so it is immediately available as a built-in preset — no manual download needed.
- `av` (PyAV) added as a dependency for ProRes / video reading.

---

## [1.1.5] — 2026-03-11

### Fixed
- **Viewer crash when switching ACES config versions**: Display and view values are now validated against the loaded config. Falls back to the config's own default display/view when the stored widget values don't match the newly selected config.

---

## [1.1.4] — 2026-03-11

### Removed
- **Display Transform node** removed (functionality covered by the Viewer node).

---

## [1.1.3] — 2026-03-11

### Fixed
- **OpenEXR loading error**: Set `OPENCV_IO_ENABLE_OPENEXR=1` environment variable before cv2 import so the OpenEXR codec is always enabled (disabled by default in OpenCV 4.x).
- Added `openexr` as an explicit dependency so the preferred OpenEXR backend installs automatically.

---

## [1.1.2] — 2026-03-11

### Fixed
- **PyOpenColorIO install failure**: `PyOpenColorIO` is not published to PyPI under that name. Removed it from `requirements.txt` and `pyproject.toml`. Added `install.py` that tries `pip install opencolorio>=2.3.0` then conda/mamba as fallbacks.
- Graceful import handling in `__init__.py`: ComfyUI no longer hard-crashes when OCIO is missing — a clear error message is logged instead.

---

## [1.1.1] — 2026-03-10

### Added
- `opencv-python` added as a dependency.

---

## [1.1.0] — 2026-03-10

### Added
- EXR sequence loader (`ACES IO — EXR Loader`) with animated preview.
- Video export node (`ACES IO — Video Saver`) supporting MP4, Animated WebP, Animated GIF.
- `ACES IO — Preview` pass-through preview node.

---

## [1.0.0] — 2026-03-09

### Added
- Initial release.
- Config Loader, ColorSpace, Display Transform, Viewer, Look Transform, File LUT, Log Convert, Config Info nodes.
- ACES 2.0 and 1.3 built-in configs via PyOpenColorIO 2.3+.
- ACES 1.2 downloadable config support.
