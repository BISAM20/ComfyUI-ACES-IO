"""
ComfyUI-ACES-IO
OpenColorIO / ACES color-management nodes for ComfyUI.

Supported ACES versions  (built-in, no download needed):
  • ACES 2.0  — CG Config & Studio Config  [OCIO 2.5]   ← recommended
  • ACES 1.3  — CG Config & Studio Config  [OCIO 2.1 / 2.3 / 2.4]

  • ACES 1.2 and any other config: supply a path to your .ocio / .ocioz file
    via the "Custom path" preset in the Config Loader node.
    Download ACES 1.2 config from:
    https://github.com/colour-science/OpenColorIO-Configs

Nodes (mirroring Nuke's OCIO set):
  ACES IO — Config Loader           load / select an OCIO config
  ACES IO — ColorSpace              OCIOColorSpace  (cs → cs conversion)
  ACES IO — Display Transform       OCIODisplay     (full display pipeline)
  ACES IO — Viewer                  Nuke Viewer     (exposure + gamma + channel view)
  ACES IO — Look Transform          OCIOLookTransform
  ACES IO — File LUT                OCIOFileTransform
  ACES IO — Log Convert             OCIOLogConvert  (log ↔ linear)
  ACES IO — Config Info             lists colorspaces / displays / views / looks
"""

import os

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Serve web/js to the ComfyUI frontend
WEB_DIRECTORY = "web"

# Register REST API routes (colorspace / display / view pickers)
try:
    from . import server_routes  # noqa: F401
except Exception as _e:
    import logging
    logging.warning(f"[ACES IO] Could not load server routes: {_e}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
