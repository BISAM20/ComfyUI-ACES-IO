# ComfyUI-ACES-IO

Professional OpenColorIO / ACES color-management nodes for ComfyUI, mirroring Nuke's OCIO node set.
Supports **ACES 2.0**, **ACES 1.3**, and **ACES 1.2** — with Nuke-style colorspace pickers, EXR sequence read/write, animated preview, and video export.

---

## Features

- **Full OCIO pipeline** — every node mirrors its Nuke counterpart
- **ACES 2.0 & 1.3 built-in** — no download needed (bundled with PyOpenColorIO 2.3+)
- **ACES 1.2 support** — point the Config Loader at your own `.ocio` / `.ocioz` file
- **Nuke-style colorspace picker** — tabbed family browser with live search (ACES / Display / Input/ARRI / Input/Sony / Utility …)
- **EXR Loader (Nuke Read node)** — auto-detects full sequences from any single frame; supports `render.0001.exr`, `render_0001.exr`, `####`, `%04d`; `all` / `range` / `single` frame modes; `error` / `black` / `hold` missing-frame policy
- **Animated preview** — sequence loads play back as animated WebP directly in the node
- **Video Saver** — export IMAGE batches to MP4 (H.264), Animated WebP, or Animated GIF
- **EXR Saver** — full 16f / 32f EXR with ZIP, PIZ, DWAA and all standard codecs
- **Cache bypass** — every node re-executes on each queue run so colorspace changes always take effect

---

## Nodes

| Node | Nuke equivalent | Category |
|------|----------------|----------|
| ACES IO — Config Loader | Project Settings → OCIO | ACES IO/Config |
| ACES IO — ColorSpace | OCIOColorSpace | ACES IO/Transform |
| ACES IO — Display Transform | OCIODisplay | ACES IO/Transform |
| ACES IO — Viewer | Nuke Viewer (LegacyViewingPipeline) | ACES IO/Viewer |
| ACES IO — Look Transform | OCIOLookTransform | ACES IO/Transform |
| ACES IO — File LUT | OCIOFileTransform | ACES IO/LUT |
| ACES IO — Log Convert | OCIOLogConvert | ACES IO/Transform |
| ACES IO — Config Info | — (utility) | ACES IO/Utility |
| ACES IO — EXR Loader | Read node | ACES IO/EXR |
| ACES IO — EXR Saver | Write node | ACES IO/EXR |
| ACES IO — Video Saver | — (MP4 / WebP / GIF export) | ACES IO/EXR |
| ACES IO — Preview | PreviewImage | ACES IO |

---

## Installation

### Via ComfyUI Manager (recommended)

1. Open ComfyUI Manager → **Install Custom Nodes**
2. Search for **ComfyUI-ACES-IO**
3. Click Install and restart ComfyUI

### Manual

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/BISAM20/ComfyUI-ACES-IO
cd ComfyUI-ACES-IO
pip install -r requirements.txt
```

Then restart ComfyUI.

### Dependencies

| Package | Purpose |
|---------|---------|
| `PyOpenColorIO >= 2.3.0` | Core OCIO processing + built-in ACES configs |
| `numpy` | Image array operations |
| `Pillow` | Preview thumbnails, animated WebP / GIF export |
| `opencv-python` | MP4 video export + EXR fallback if OpenEXR is unavailable |
| `OpenEXR` *(optional)* | Full EXR read/write with all compression codecs |

`PyOpenColorIO`, `numpy`, `Pillow`, and `opencv-python` install automatically via `pip install -r requirements.txt`.
For full EXR compression support install OpenEXR:

```bash
pip install openexr
```

---

## Quick Start

### Basic ACES workflow

```
Load Image  →  Config Loader  →  ColorSpace (sRGB → ACEScg)
                                       ↓
                               [your nodes]
                                       ↓
                               Viewer (ACEScg → sRGB Display)  →  Preview
```

### EXR sequence workflow

```
EXR Loader  →  ColorSpace (scene-linear → ACEScg)  →  Viewer  →  Video Saver
```

The EXR Loader outputs a `[B, H, W, C]` float32 batch tensor — one item per frame.
Set `frame_mode = all` to load everything on disk automatically (no manual range needed).

### Colorspace picker

Every colorspace, display, and view input has a **Browse** button that opens a Nuke-style dialog:

- **Top tabs** — family groups (ACES, Display, Input, Utility, All)
- **Sub-tabs** — camera manufacturers (ARRI, Sony, RED, Canon …)
- **Live search** — type anywhere to filter across all colorspaces

---

## EXR Loader — Frame Modes

| `frame_mode` | Behaviour |
|---|---|
| **all** *(default)* | Auto-detects every frame on disk from any single file or pattern |
| **range** | Loads `first_frame … last_frame` inclusive |
| **single** | Loads exactly the frame number specified by `first_frame` |

### Supported naming conventions

| Pattern | Example |
|---|---|
| Dot-separated | `render.0001.exr` |
| Underscore-separated | `render_0001.exr` |
| Hyphen-separated | `render-0001.exr` |
| Frame-only | `0001.exr` |
| With version token | `shot_v01_beauty_0042.exr` → uses `0042` as frame |
| Nuke hash | `render.####.exr` |
| Printf | `render.%04d.exr` |

### Missing frames policy

| Option | Behaviour |
|---|---|
| `error` *(default)* | Raises an exception — matches Nuke default |
| `black` | Substitutes a black frame |
| `hold` | Repeats the last successfully loaded frame |

---

## Video Saver

Export any IMAGE batch to a video file directly from your graph:

| Format | Notes |
|---|---|
| **MP4 (H.264)** | Standard video via OpenCV — plays in any media player |
| **Animated WebP** | High-quality, plays in browsers and most modern viewers |
| **Animated GIF** | Universal compatibility; 256-colour limit |

The node passes the IMAGE tensor through unchanged so it can sit anywhere in a graph without interrupting the flow.

---

## Supported ACES Configs

| Preset | OCIO version | Notes |
|--------|-------------|-------|
| ACES 2.0 CG | 2.5 | Recommended for CG work |
| ACES 2.0 Studio | 2.5 | Recommended for live-action / studio |
| ACES 1.3 CG | 2.1 / 2.3 / 2.4 | Legacy, three OCIO versions |
| ACES 1.3 Studio | 2.1 / 2.3 / 2.4 | Legacy, three OCIO versions |
| ACES 1.2 | v1 (colour-science) | Supply path to downloaded config |
| Custom path | any | Point to your own `.ocio` / `.ocioz` file |

ACES 1.2 config can be downloaded from [colour-science/OpenColorIO-Configs](https://github.com/colour-science/OpenColorIO-Configs).

---

## License

MIT — see [LICENSE](LICENSE)

The ACES configs bundled within PyOpenColorIO are released under the [Academy Software Foundation (ASWF)](https://www.aswf.io/) open-source license.
The ACES 1.2 config is released by [colour-science](https://github.com/colour-science/OpenColorIO-Configs) under the BSD license.
