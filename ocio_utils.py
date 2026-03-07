"""
OCIO utility functions for ACES IO nodes.
Config loading, caching, and image processing helpers.
"""

import os
import numpy as np
import torch
import PyOpenColorIO as ocio
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ACES 1.2 local path  (populated at import time if already downloaded)
# ---------------------------------------------------------------------------
_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
_CONFIGS_DIR = os.path.join(_THIS_DIR, "configs")
_ACES12_DIR  = os.path.join(_CONFIGS_DIR, "aces_1.2")
_ACES12_CFG  = os.path.join(_ACES12_DIR, "config.ocio")

# Download info
ACES12_DOWNLOAD_URL  = (
    "https://github.com/colour-science/OpenColorIO-Configs/releases/"
    "download/v1.2/OpenColorIO-Config-ACES-1.2.zip"
)
ACES12_DOWNLOAD_SIZE = 130_123_781   # ~130 MB

# ---------------------------------------------------------------------------
# Built-in configs  (OCIO 2.x built-in registry)
# ---------------------------------------------------------------------------
BUILTIN_CONFIGS: Dict[str, str] = {
    "ACES 2.0 CG  [Recommended]":        "cg-config-v4.0.0_aces-v2.0_ocio-v2.5",
    "ACES 2.0 Studio [Recommended]":      "studio-config-v4.0.0_aces-v2.0_ocio-v2.5",
    "ACES 1.3 CG  (OCIO 2.4)":           "cg-config-v2.2.0_aces-v1.3_ocio-v2.4",
    "ACES 1.3 Studio (OCIO 2.4)":         "studio-config-v2.2.0_aces-v1.3_ocio-v2.4",
    "ACES 1.3 CG  (OCIO 2.3)":           "cg-config-v2.1.0_aces-v1.3_ocio-v2.3",
    "ACES 1.3 Studio (OCIO 2.3)":         "studio-config-v2.1.0_aces-v1.3_ocio-v2.3",
    "ACES 1.3 CG  (OCIO 2.1 / legacy)":  "cg-config-v1.0.0_aces-v1.3_ocio-v2.1",
    "ACES 1.3 Studio (OCIO 2.1 / legacy)":"studio-config-v1.0.0_aces-v1.3_ocio-v2.1",
    "Custom path  (ACES 1.2 / other)":    "__custom__",
}

# Inject ACES 1.2 if already downloaded
def _refresh_aces12():
    key = "ACES 1.2  (colour-science / OCIO v1)"
    if os.path.isfile(_ACES12_CFG):
        BUILTIN_CONFIGS[key] = _ACES12_CFG
        # Move it right after the 1.3 entries, before Custom
        ordered = list(BUILTIN_CONFIGS.items())
        # ensure it's not duplicated
        ordered = [(k, v) for k, v in ordered if k != key]
        insert_at = next((i for i, (k, _) in enumerate(ordered) if k.startswith("Custom")), len(ordered))
        ordered.insert(insert_at, (key, _ACES12_CFG))
        BUILTIN_CONFIGS.clear()
        BUILTIN_CONFIGS.update(ordered)
    else:
        BUILTIN_CONFIGS.pop(key, None)
    global BUILTIN_CONFIG_KEYS
    BUILTIN_CONFIG_KEYS = list(BUILTIN_CONFIGS.keys())

_refresh_aces12()
BUILTIN_CONFIG_KEYS = list(BUILTIN_CONFIGS.keys())

# ---------------------------------------------------------------------------
# Channel-view matrices  (row-major 4×4, same convention as Nuke viewer)
# out[i] = sum_j( M[i*4+j] * in[j] )
# ---------------------------------------------------------------------------
CHANNEL_MATRICES: Dict[str, list] = {
    "RGBA": [1,0,0,0,  0,1,0,0,  0,0,1,0,  0,0,0,1],   # identity
    "R":    [1,0,0,0,  1,0,0,0,  1,0,0,0,  0,0,0,1],
    "G":    [0,1,0,0,  0,1,0,0,  0,1,0,0,  0,0,0,1],
    "B":    [0,0,1,0,  0,0,1,0,  0,0,1,0,  0,0,0,1],
    "A":    [0,0,0,1,  0,0,0,1,  0,0,0,1,  0,0,0,1],
    # Rec.709 luma coefficients
    "Luminance": [0.2126,0.7152,0.0722,0,
                  0.2126,0.7152,0.0722,0,
                  0.2126,0.7152,0.0722,0,
                  0,0,0,1],
}

# ---------------------------------------------------------------------------
# Config cache
# ---------------------------------------------------------------------------
_config_cache: Dict[str, ocio.Config] = {}


def load_config(preset: str, custom_path: str = "") -> ocio.Config:
    """Return a cached ocio.Config for the given preset or custom path."""
    builtin_name = BUILTIN_CONFIGS.get(preset, "__custom__")

    if builtin_name == "__custom__":
        key = custom_path.strip()
        if not key:
            raise ValueError(
                "No config path supplied. Set 'config_path' to a valid .ocio or .ocioz file."
            )
        if key not in _config_cache:
            if not os.path.isfile(key):
                raise FileNotFoundError(f"OCIO config not found: '{key}'")
            _config_cache[key] = ocio.Config.CreateFromFile(key)
        return _config_cache[key]
    elif os.path.isfile(builtin_name):
        # Local file path (e.g. ACES 1.2 downloaded config)
        if builtin_name not in _config_cache:
            _config_cache[builtin_name] = ocio.Config.CreateFromFile(builtin_name)
        return _config_cache[builtin_name]
    else:
        if builtin_name not in _config_cache:
            _config_cache[builtin_name] = ocio.Config.CreateFromBuiltinConfig(builtin_name)
        return _config_cache[builtin_name]


def get_displays(cfg: ocio.Config):
    return list(cfg.getDisplays())


def get_views(cfg: ocio.Config, display: str):
    return list(cfg.getViews(display))


def get_colorspaces(cfg: ocio.Config):
    return [cs.getName() for cs in cfg.getColorSpaces()]


def get_looks(cfg: ocio.Config):
    return [lk.getName() for lk in cfg.getLooks()]


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

def apply_processor(tensor: torch.Tensor, processor: ocio.Processor) -> torch.Tensor:
    """
    Apply an OCIO Processor to a ComfyUI IMAGE tensor [B, H, W, C].
    Works in-place on a numpy copy; returns a new tensor on the original device.
    """
    cpu_proc = processor.getDefaultCPUProcessor()
    device = tensor.device
    img_np = tensor.cpu().float().numpy()           # [B, H, W, C] float32
    B, H, W, C = img_np.shape
    result = np.empty_like(img_np)

    for b in range(B):
        frame = np.ascontiguousarray(img_np[b], dtype=np.float32)
        desc = ocio.PackedImageDesc(frame, W, H, C)
        cpu_proc.apply(desc)
        result[b] = frame

    out = torch.from_numpy(result)
    return out.to(device) if device.type != "cpu" else out


def build_channel_view_transform(channel: str) -> Optional[ocio.MatrixTransform]:
    """Return a MatrixTransform for single-channel or luminance view, or None for RGBA."""
    if channel == "RGBA":
        return None
    mat = CHANNEL_MATRICES.get(channel)
    if mat is None:
        return None
    mt = ocio.MatrixTransform()
    mt.setMatrix(mat)
    return mt


def build_exposure_transform(exposure_stops: float) -> Optional[ocio.ExposureContrastTransform]:
    """Return an ExposureContrastTransform (LINEAR style) for the given stop value, or None."""
    if abs(exposure_stops) < 1e-7:
        return None
    ec = ocio.ExposureContrastTransform(
        style=ocio.EXPOSURE_CONTRAST_LINEAR,
        exposure=exposure_stops,
        contrast=1.0,
        gamma=1.0,
        pivot=0.18,
    )
    return ec


def build_gamma_transform(gamma: float) -> Optional[ocio.ExposureContrastTransform]:
    """
    Return a display-space gamma correction using ExposureContrastTransform VIDEO style.
    gamma > 1 darkens the image, gamma < 1 brightens it (matching Nuke viewer gamma knob).
    """
    if abs(gamma - 1.0) < 1e-7:
        return None
    # VIDEO style: out = in^(1/gamma) — same as Nuke viewer gamma
    ec = ocio.ExposureContrastTransform(
        style=ocio.EXPOSURE_CONTRAST_VIDEO,
        exposure=0.0,
        contrast=1.0,
        gamma=gamma,
        pivot=0.18,
    )
    return ec
