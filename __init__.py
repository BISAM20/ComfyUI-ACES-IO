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
import importlib.util
import logging

_logger = logging.getLogger(__name__)

# Check for PyOpenColorIO before attempting to import nodes so that a missing
# OCIO installation shows a single, actionable message rather than a traceback.
if importlib.util.find_spec("PyOpenColorIO") is None:
    _logger.error(
        "\n"
        "[ACES IO] PyOpenColorIO is not installed — nodes will not load.\n"
        "Install it with one of:\n"
        "  pip install opencolorio>=2.3.0\n"
        "  conda install -c conda-forge opencolorio>=2.3.0\n"
        "Then restart ComfyUI."
    )
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
else:
    from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

    # Auto-download ACES 1.2 config if not already present, then refresh the
    # built-in config list so the dropdown includes it on first run.
    try:
        from .install import download_aces12
        from .ocio_utils import _refresh_aces12
        download_aces12()
        _refresh_aces12()
    except Exception as _dl_e:
        _logger.warning(f"[ACES IO] Could not auto-download ACES 1.2 config: {_dl_e}")

    from .wan_inverse_tonemap import (
        NODE_CLASS_MAPPINGS        as _WAN_CM,
        NODE_DISPLAY_NAME_MAPPINGS as _WAN_DNM,
    )
    NODE_CLASS_MAPPINGS        = {**NODE_CLASS_MAPPINGS,        **_WAN_CM}
    NODE_DISPLAY_NAME_MAPPINGS = {**NODE_DISPLAY_NAME_MAPPINGS, **_WAN_DNM}

# Serve web/js to the ComfyUI frontend
WEB_DIRECTORY = "web"

# Register REST API routes (colorspace / display / view pickers)
try:
    from . import server_routes  # noqa: F401
except Exception as _e:
    import logging
    logging.warning(f"[ACES IO] Could not load server routes: {_e}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
