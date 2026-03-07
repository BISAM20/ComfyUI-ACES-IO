# ComfyUI-ACES-IO

Professional OpenColorIO / ACES color-management nodes for ComfyUI, mirroring Nuke's OCIO node set exactly.
Supports **ACES 2.0**, **ACES 1.3**, and **ACES 1.2** — with built-in Nuke-style colorspace pickers, EXR read/write, and a live HDR preview node.

---

## Features

- **Full OCIO pipeline** — every node mirrors its Nuke counterpart
- **ACES 2.0 & 1.3 built-in** — no download needed (bundled with PyOpenColorIO 2.3+)
- **ACES 1.2 support** — one-click download via the included Download node (~130 MB)
- **Nuke-style colorspace picker** — tabbed family browser (ACES / Display / Input/ARRI / Input/Sony / Utility …) with live search
- **EXR read / write** — full OpenEXR support with all compression codecs and 16f / 32f bit depth
- **HDR preview** — tone-mapped viewer node with exposure, gamma, and channel controls
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
| ACES IO — Config Info | — (utility) | ACES IO/Config |
| ACES IO — EXR Saver | Write node | ACES IO/EXR |
| ACES IO — EXR Loader | Read node | ACES IO/EXR |
| ACES IO — EXR Viewer | — (HDR preview) | ACES IO/EXR |
| ACES IO — Preview | PreviewImage | ACES IO |
| ACES IO — Download ACES 1.2 Config | — | ACES IO/Config |

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
| `Pillow` | Preview thumbnail saving |
| `OpenEXR` *(optional)* | Full EXR read/write with all compression codecs |
| `opencv-python` *(fallback)* | EXR read/write if OpenEXR is not available |

`PyOpenColorIO`, `numpy`, and `Pillow` install automatically via pip.
For full EXR support install OpenEXR separately:

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

### Colorspace picker

Every colorspace, display, and view input has a **Browse** button that opens a Nuke-style dialog:

- **Top tabs** — family groups (ACES, Display, Input, Utility, All)
- **Sub-tabs** — camera manufacturers (ARRI, Sony, RED, Canon …)
- **Live search** — type anywhere to filter across all colorspaces

### EXR workflow

```
EXR Loader  →  (optional) ColorSpace  →  EXR Viewer  →  EXR Saver
```

The EXR Loader outputs a full float32 HDR tensor.
The EXR Viewer applies an ACES Output Transform for display.
The EXR Saver writes 16f or 32f EXR with ZIP / PIZ / DWAA compression.

---

## ACES 1.2

ACES 1.2 is not bundled (it is ~130 MB). To install it:

1. Add an **ACES IO — Download ACES 1.2 Config** node to your workflow
2. Set `trigger = True` and queue the prompt
3. Wait for the status output to read `Done! Restart ComfyUI to use ACES 1.2.`
4. Restart ComfyUI — the preset **"ACES 1.2  (colour-science / OCIO v1)"** will appear in the Config Loader dropdown

The config is downloaded from the [colour-science OpenColorIO-Configs](https://github.com/colour-science/OpenColorIO-Configs) GitHub releases and saved to `ComfyUI-ACES-IO/configs/aces_1.2/`.

---

## Supported ACES Configs

| Preset | OCIO version | Notes |
|--------|-------------|-------|
| ACES 2.0 CG | 2.5 | Recommended for CG work |
| ACES 2.0 Studio | 2.5 | Recommended for live-action / studio |
| ACES 1.3 CG | 2.1 / 2.3 / 2.4 | Legacy, three OCIO versions |
| ACES 1.3 Studio | 2.1 / 2.3 / 2.4 | Legacy, three OCIO versions |
| ACES 1.2 | v1 (colour-science) | Download required (~130 MB) |
| Custom path | any | Point to your own `.ocio` / `.ocioz` file |

---

## License

MIT — see [LICENSE](LICENSE)

The ACES configs bundled within PyOpenColorIO are released under the [Academy Software Foundation (ASWF)](https://www.aswf.io/) open-source license. The ACES 1.2 config downloaded on demand is released by [colour-science](https://github.com/colour-science/OpenColorIO-Configs) under the BSD license.
