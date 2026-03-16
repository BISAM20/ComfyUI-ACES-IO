# ComfyUI-ACES-IO

Professional OpenColorIO / ACES color-management nodes for ComfyUI, mirroring Nuke's OCIO node set.
Supports **ACES 2.0**, **ACES 1.3**, and **ACES 1.2** — with Nuke-style colorspace pickers, EXR sequence read/write, animated preview, ProRes MOV export, and video output.

---

## What's New in v1.3

- **OCIODisplay node** — bake a Display View Transform into image data with a one-click **Invert** toggle (display → scene-linear roundtrip)
- **EXR Loader color transforms** — optional `ocio_config` input + `colorspace` / `output_transform` convert on load, mirroring Nuke's Read node
- **EXR Saver color transforms** — optional `ocio_config` input + `input_transform` / `colorspace` convert before write, mirroring Nuke's Write node
- **ProRes MOV export** — Video Saver now supports ProRes 422, 422 HQ, 4444, and 4444 XQ via PyAV (10-bit; alpha preserved for 4444)
- **ACES 1.2 always in dropdown** — no longer requires a pre-existing download; auto-fetches the config (~130 MB) on first use

---

## Features

- **Full OCIO pipeline** — every node mirrors its Nuke counterpart
- **ACES 2.0 & 1.3 built-in** — no download needed (bundled with PyOpenColorIO 2.3+)
- **ACES 1.2 support** — always in the preset dropdown; auto-downloads on first use
- **Nuke-style colorspace picker** — tabbed family browser with live search (ACES / Display / Input/ARRI / Input/Sony / Utility …)
- **EXR Loader (Nuke Read node)** — auto-detects full sequences from any single frame; supports `render.0001.exr`, `render_0001.exr`, `####`, `%04d`; `all` / `range` / `single` frame modes; `error` / `black` / `hold` missing-frame policy; optional color transform on load
- **EXR Saver (Nuke Write node)** — full 16f / 32f EXR with ZIP, PIZ, DWAA and all standard codecs; optional color transform before write
- **Animated preview** — sequence loads play back as animated WebP directly in the node
- **Video Loader** — loads `.mov`, `.mp4`, `.mxf` and other formats; full ProRes support via PyAV
- **Video Saver** — export IMAGE batches to MP4 (H.264), MOV ProRes (422 / 422 HQ / 4444 / 4444 XQ), Animated WebP, or Animated GIF
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
| ACES IO — Video Loader | — (MOV/ProRes/MP4 input) | ACES IO/EXR |
| ACES IO — Video Saver | — (MP4 / ProRes / WebP / GIF export) | ACES IO/EXR |
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
| `av` (PyAV) *(optional)* | Video input (MOV/MP4/MXF) + ProRes MOV export |

`PyOpenColorIO`, `numpy`, `Pillow`, and `opencv-python` install automatically via `pip install -r requirements.txt`.
For full EXR compression support and ProRes export:

```bash
pip install openexr av
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

## Display Transform Node (OCIODisplay)

`ACES IO — Display Transform` bakes a Display View Transform into the image data — unlike the Viewer node which is for preview only.

| Input | Description |
|---|---|
| `input_colorspace` | Source colorspace (e.g. ACEScg) |
| `display` | Target display device (e.g. sRGB - Display) |
| `view` | View transform (e.g. ACES 2.0 - SDR 100 nits (Rec.709)) |
| `invert` | Reverses the transform — display-referred → input colorspace (scene-linear roundtrip) |

The `invert` toggle maps directly to Nuke's OCIODisplay `invert` knob, running the full display pipeline in reverse via `TRANSFORM_DIR_INVERSE`.

---

## EXR Loader — Color Transforms

Connect an `ocio_config` to apply a color transform on load:

| Input | Description |
|---|---|
| `colorspace` | Color space the EXR file is stored as (file/camera space) |
| `output_transform` | Color space to deliver downstream (working/pipe space) |

When `ocio_config` is disconnected both fields are ignored and pixels pass through unchanged — mirrors Nuke's Read node behaviour.

---

## EXR Saver — Color Transforms

Connect an `ocio_config` to apply a color transform before writing:

| Input | Description |
|---|---|
| `input_transform` | Color space of the incoming image (working/pipe space) |
| `colorspace` | Color space to store in the EXR file |

When `ocio_config` is disconnected both fields are ignored — mirrors Nuke's Write node behaviour.

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
| **MOV ProRes 422** | Apple ProRes 422 — 10-bit YUV 4:2:2 via PyAV |
| **MOV ProRes 422 HQ** | Apple ProRes 422 HQ — higher bitrate 10-bit via PyAV |
| **MOV ProRes 4444** | Apple ProRes 4444 — 10-bit 4:4:4, alpha channel preserved via PyAV |
| **MOV ProRes 4444 XQ** | Apple ProRes 4444 XQ — highest quality + alpha via PyAV |
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
| ACES 1.2 | v1 (colour-science) | Auto-downloads on first use (~130 MB) |
| Custom path | any | Point to your own `.ocio` / `.ocioz` file |

ACES 1.2 config can also be downloaded manually from [colour-science/OpenColorIO-Configs](https://github.com/colour-science/OpenColorIO-Configs).

---

## License

MIT — see [LICENSE](LICENSE)

The ACES configs bundled within PyOpenColorIO are released under the [Academy Software Foundation (ASWF)](https://www.aswf.io/) open-source license.
The ACES 1.2 config is released by [colour-science](https://github.com/colour-science/OpenColorIO-Configs) under the BSD license.
