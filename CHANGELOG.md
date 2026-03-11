# Changelog

All notable changes to ComfyUI-ACES-IO are documented here.

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
