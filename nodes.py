"""
ComfyUI-ACES-IO  —  OpenColorIO / ACES color-management nodes.

Mirrors Nuke's OCIO node set exactly:
  ACESIOConfig          ≈  Project Settings → OCIO config
  ACESIOColorSpace      ≈  OCIOColorSpace node
  ACESIODisplay         ≈  OCIODisplay node
  ACESIOViewer          ≈  Nuke Viewer (display + exposure + gamma + channel view)
  ACESIOLook            ≈  OCIOLookTransform node
  ACESIOFileLUT         ≈  OCIOFileTransform node
  ACESIOLogConvert      ≈  OCIOLogConvert node
  ACESIOInfo            ≈  utility — lists colorspaces / displays / views / looks
"""

import torch
import numpy as np
import os
import re
import uuid
import PyOpenColorIO as ocio
import folder_paths
from PIL import Image

from .ocio_utils import (
    BUILTIN_CONFIG_KEYS,
    load_config,
    apply_processor,
    get_displays,
    get_views,
    get_colorspaces,
    get_looks,
    build_channel_view_transform,
    build_exposure_transform,
    build_gamma_transform,
)
from .exr_utils import (
    save_exr, load_exr,
    COMPRESSION_KEYS, BIT_DEPTHS,
)

def _cfg_id(ocio_config):
    """Return a stable string key for an OCIO_CONFIG dict (used in IS_CHANGED)."""
    if isinstance(ocio_config, dict):
        return f"{ocio_config.get('preset','')}|{ocio_config.get('path','')}"
    return str(id(ocio_config))


def _save_preview(tensor: torch.Tensor) -> list:
    """
    Save a [B,H,W,C] float32 IMAGE tensor to ComfyUI's temp folder as PNG.
    Returns the list of image dicts expected by ComfyUI's UI preview system.
    """
    temp_dir = folder_paths.get_temp_directory()
    os.makedirs(temp_dir, exist_ok=True)
    results = []
    for i in range(tensor.shape[0]):
        frame = tensor[i].cpu().float().numpy()
        frame = (frame * 255.0).clip(0, 255).astype(np.uint8)
        if frame.shape[2] == 1:
            img = Image.fromarray(frame[:, :, 0], mode="L")
        elif frame.shape[2] == 4:
            img = Image.fromarray(frame, mode="RGBA")
        else:
            img = Image.fromarray(frame[:, :, :3], mode="RGB")
        filename = f"aces_io_preview_{uuid.uuid4().hex[:12]}.png"
        img.save(os.path.join(temp_dir, filename))
        results.append({"filename": filename, "subfolder": "", "type": "temp"})
    return results


# ============================================================================
#  1.  ACESIOConfig  —  config loader / selector
# ============================================================================

class ACESIOConfig:
    """
    Load an OCIO config.

    Select one of the ACES built-in configs (ACES 1.3 CG/Studio, ACES 2.0 CG/Studio)
    or supply a path to a custom .ocio / .ocioz file (needed for ACES 1.2 or
    studio-specific configs downloaded from the ASWF or colour-science repos).

    Output: an OCIO_CONFIG handle that all other ACES IO nodes accept.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "config_preset": (BUILTIN_CONFIG_KEYS,
                                  {"default": "ACES 2.0 CG  [Recommended]"}),
            },
            "optional": {
                "config_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "/path/to/config.ocio  (needed for Custom / ACES 1.2)",
                }),
            },
        }

    RETURN_TYPES  = ("OCIO_CONFIG",)
    RETURN_NAMES  = ("ocio_config",)
    FUNCTION      = "load"
    CATEGORY      = "ACES IO/Config"

    def load(self, config_preset: str, config_path: str = ""):
        cfg = load_config(config_preset, config_path.strip())
        return ({"config": cfg, "preset": config_preset, "path": config_path},)


# ============================================================================
#  2.  ACESIOColorSpace  —  colorspace-to-colorspace conversion  (OCIOColorSpace)
# ============================================================================

class ACESIOColorSpace:
    """
    Convert an image between any two colorspaces defined in the OCIO config.
    Mirrors Nuke's OCIOColorSpace node.

    Typical uses
    ────────────
    • sRGB texture → ACEScg for compositing
    • ACES2065-1 → ACEScg (AP0 → AP1)
    • ACEScg → ACEScct / ACEScc for grading
    • Camera log → ACEScg  (with Studio config)
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":          ("IMAGE",),
                "ocio_config":    ("OCIO_CONFIG",),
                "in_colorspace":  ("ACES_COLORSPACE", {"default": "sRGB Encoded Rec.709 (sRGB)"}),
                "out_colorspace": ("ACES_COLORSPACE", {"default": "ACEScg"}),
                "direction":      (["Forward", "Inverse"], {"default": "Forward"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION     = "convert"
    CATEGORY     = "ACES IO/Transform"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def convert(self, image, ocio_config, in_colorspace, out_colorspace, direction):
        cfg = ocio_config["config"]
        src, dst = in_colorspace.strip(), out_colorspace.strip()
        if direction == "Inverse":
            src, dst = dst, src
        try:
            proc = cfg.getProcessor(src, dst)
        except ocio.Exception as e:
            raise ValueError(
                f"OCIOColorSpace: cannot convert '{src}' → '{dst}'.\n"
                f"OCIO error: {e}\n"
                f"Available colorspaces: {get_colorspaces(cfg)}"
            )
        return (apply_processor(image, proc),)


# ============================================================================
#  3.  ACESIODisplay  —  display / view transform pipeline  (OCIODisplay)
# ============================================================================

class ACESIODisplay:
    """
    Apply a full ACES display-view transform.
    Mirrors Nuke's OCIODisplay node.

    The pipeline converts the input from its declared colorspace through the
    chosen (Display, View) pair — exactly the OCIO DisplayViewTransform.

    Optional Looks override: supply a comma/colon separated list of look names
    (with optional +/– prefix for direction) or leave blank to use the looks
    embedded in the View definition.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":            ("IMAGE",),
                "ocio_config":      ("OCIO_CONFIG",),
                "input_colorspace": ("ACES_COLORSPACE", {"default": "ACEScg"}),
                "display":          ("ACES_DISPLAY",     {"default": "sRGB - Display"}),
                "view":             ("ACES_VIEW",         {"default": "ACES 2.0 - SDR 100 nits (Rec.709)"}),
                "direction":        (["Forward", "Inverse"], {"default": "Forward"}),
            },
            "optional": {
                "looks_override":         ("STRING", {"default": "", "multiline": False,
                                                       "placeholder": "e.g.  ACES 1.3 Reference Gamut Compression"}),
                "looks_override_enabled": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION     = "display_transform"
    CATEGORY     = "ACES IO/Transform"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def display_transform(self, image, ocio_config,
                          input_colorspace, display, view, direction,
                          looks_override="", looks_override_enabled=False):
        cfg = ocio_config["config"]

        dv = ocio.DisplayViewTransform()
        dv.setSrc(input_colorspace.strip())
        dv.setDisplay(display.strip())
        dv.setView(view.strip())
        if direction == "Inverse":
            dv.setDirection(ocio.TRANSFORM_DIR_INVERSE)

        pipeline = ocio.LegacyViewingPipeline()
        pipeline.setDisplayViewTransform(dv)
        if looks_override_enabled:
            pipeline.setLooksOverrideEnabled(True)
            pipeline.setLooksOverride(looks_override.strip())

        try:
            proc = pipeline.getProcessor(cfg)
        except ocio.Exception as e:
            raise ValueError(
                f"ACESIODisplay: failed to build processor for "
                f"display='{display}', view='{view}'.\nOCIO error: {e}"
            )
        return (apply_processor(image, proc),)


# ============================================================================
#  4.  ACESIOViewer  —  Nuke-style viewer  (LegacyViewingPipeline)
# ============================================================================

class ACESIOViewer:
    """
    Full Nuke-style viewer using OCIO's LegacyViewingPipeline.

    Pipeline order (mirrors Nuke exactly):
      input_colorspace
        → scene_linear  (linearCC / exposure applied here, in linear light)
        → color_timing  (colorTimingCC — optional CDL grade)
        → looks
        → channelView   (R / G / B / A / Luminance swizzle)
        → DisplayViewTransform
        → displayCC     (gamma correction, applied in display-referred space)

    Controls
    ────────
    exposure    Exposure in stops, applied in scene-linear (same as Nuke viewer E knob)
    gamma       Display-space gamma correction  (same as Nuke viewer G knob)
    channel     RGBA | R | G | B | A | Luminance  (same as Nuke viewer channel menu)
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":            ("IMAGE",),
                "ocio_config":      ("OCIO_CONFIG",),
                "input_colorspace": ("ACES_COLORSPACE", {"default": "ACEScg"}),
                "display":          ("ACES_DISPLAY",     {"default": "sRGB - Display"}),
                "view":             ("ACES_VIEW",         {"default": "ACES 2.0 - SDR 100 nits (Rec.709)"}),
                "exposure":         ("FLOAT",  {"default": 0.0, "min": -10.0, "max": 10.0,
                                                "step": 0.1,
                                                "tooltip": "Exposure offset in stops (linearCC, scene-linear space)"}),
                "gamma":            ("FLOAT",  {"default": 1.0, "min": 0.1,  "max": 4.0,
                                                "step": 0.01,
                                                "tooltip": "Display gamma correction (displayCC, after display transform)"}),
                "channel":          (["RGBA", "R", "G", "B", "A", "Luminance"],
                                     {"default": "RGBA"}),
            },
            "optional": {
                "looks_override":         ("STRING",  {"default": "", "multiline": False}),
                "looks_override_enabled": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION     = "viewer"
    CATEGORY     = "ACES IO/Viewer"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def viewer(self, image, ocio_config,
               input_colorspace, display, view,
               exposure, gamma, channel,
               looks_override="", looks_override_enabled=False):

        cfg = ocio_config["config"]

        # --- DisplayViewTransform ---
        dv = ocio.DisplayViewTransform()
        dv.setSrc(input_colorspace.strip())
        dv.setDisplay(display.strip())
        dv.setView(view.strip())

        # --- Build LegacyViewingPipeline (exact Nuke viewer order) ---
        pipeline = ocio.LegacyViewingPipeline()
        pipeline.setDisplayViewTransform(dv)

        # linearCC  — exposure in scene-linear  (Nuke "E" knob)
        exp_t = build_exposure_transform(exposure)
        if exp_t is not None:
            pipeline.setLinearCC(exp_t)

        # channelView — RGB / single-channel swizzle (Nuke channel menu)
        ch_t = build_channel_view_transform(channel)
        if ch_t is not None:
            pipeline.setChannelView(ch_t)

        # looks override
        if looks_override_enabled:
            pipeline.setLooksOverrideEnabled(True)
            pipeline.setLooksOverride(looks_override.strip())

        # displayCC — gamma in display space (Nuke "G" knob)
        gam_t = build_gamma_transform(gamma)
        if gam_t is not None:
            pipeline.setDisplayCC(gam_t)

        try:
            proc = pipeline.getProcessor(cfg)
        except ocio.Exception as e:
            raise ValueError(
                f"ACESIOViewer: failed to build viewer pipeline.\n"
                f"  input_colorspace = '{input_colorspace}'\n"
                f"  display          = '{display}'\n"
                f"  view             = '{view}'\n"
                f"OCIO error: {e}\n"
                f"Available displays: {get_displays(cfg)}"
            )

        return (apply_processor(image, proc),)


# ============================================================================
#  5.  ACESIOLook  —  apply one or more OCIO Looks  (OCIOLookTransform)
# ============================================================================

class ACESIOLook:
    """
    Apply one or more Looks defined in the OCIO config.
    Mirrors Nuke's OCIOLookTransform node.

    looks   Comma or colon-separated list of look names.
            Prefix with '+' for forward (default) or '-' for inverse.
            Example: "ACES 1.3 Reference Gamut Compression"

    from_space / to_space
            Colorspace to convert the image to before / after applying the looks.
            Leave blank to use the look's own process_space.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":      ("IMAGE",),
                "ocio_config":("OCIO_CONFIG",),
                "looks":      ("STRING",          {"default": "ACES 1.3 Reference Gamut Compression",
                                                   "multiline": False,
                                                   "placeholder": "Comma/colon list of look names; prefix -/+ for direction"}),
                "from_space": ("ACES_COLORSPACE", {"default": "ACEScg"}),
                "to_space":   ("ACES_COLORSPACE", {"default": "ACEScg"}),
                "direction":  (["Forward", "Inverse"], {"default": "Forward"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION     = "apply_look"
    CATEGORY     = "ACES IO/Transform"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def apply_look(self, image, ocio_config, looks, from_space, to_space, direction):
        cfg = ocio_config["config"]
        from_space = from_space.strip()
        to_space   = to_space.strip() or from_space

        t = ocio.LookTransform()
        t.setLooks(looks.strip())
        t.setSrc(from_space)
        t.setDst(to_space)
        if direction == "Inverse":
            t.setDirection(ocio.TRANSFORM_DIR_INVERSE)

        try:
            proc = cfg.getProcessor(t)
        except ocio.Exception as e:
            available = get_looks(cfg)
            raise ValueError(
                f"ACESIOLook: cannot apply look(s) '{looks}'.\n"
                f"OCIO error: {e}\n"
                f"Available looks: {available}"
            )
        return (apply_processor(image, proc),)


# ============================================================================
#  6.  ACESIOFileLUT  —  apply an external LUT file  (OCIOFileTransform)
# ============================================================================

class ACESIOFileLUT:
    """
    Apply an external LUT file via OCIO.
    Mirrors Nuke's OCIOFileTransform node.

    Supports any format OCIO can read: .cube, .spi1d, .spi3d, .clf, .csp,
    .lut, .mga, .3dl, .vf, .spimtx, …

    When an ocio_config is connected the file is looked up using that config's
    search paths; otherwise a minimal raw config is used and the path must be
    absolute.
    """

    INTERP_MAP = {
        "Best (auto)":   ocio.INTERP_BEST,
        "Linear":        ocio.INTERP_LINEAR,
        "Tetrahedral":   ocio.INTERP_TETRAHEDRAL,
        "Cubic":         ocio.INTERP_CUBIC,
        "Nearest":       ocio.INTERP_NEAREST,
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":         ("IMAGE",),
                "lut_path":      ("STRING", {"default": "", "multiline": False,
                                              "placeholder": "/absolute/path/to/file.cube"}),
                "direction":     (["Forward", "Inverse"], {"default": "Forward"}),
                "interpolation": (list(cls.INTERP_MAP.keys()),
                                  {"default": "Tetrahedral"}),
            },
            "optional": {
                "ocio_config": ("OCIO_CONFIG",),
                "cccid":       ("STRING", {"default": "", "multiline": False,
                                            "tooltip": "Optional CDL/CCC ID when loading .cdl/.ccc files"}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION     = "apply_lut"
    CATEGORY     = "ACES IO/LUT"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def apply_lut(self, image, lut_path, direction, interpolation,
                  ocio_config=None, cccid=""):
        path = lut_path.strip()
        if not path:
            raise ValueError("ACESIOFileLUT: lut_path is empty.")

        ft = ocio.FileTransform()
        ft.setSrc(path)
        ft.setInterpolation(self.INTERP_MAP[interpolation])
        if cccid.strip():
            ft.setCCCId(cccid.strip())
        if direction == "Inverse":
            ft.setDirection(ocio.TRANSFORM_DIR_INVERSE)

        # Use the supplied config (preserves search paths) or a bare raw config
        if ocio_config is not None:
            cfg = ocio_config["config"]
        else:
            cfg = ocio.Config.CreateRaw()

        try:
            proc = cfg.getProcessor(ft)
        except ocio.Exception as e:
            raise ValueError(
                f"ACESIOFileLUT: failed to load LUT '{path}'.\nOCIO error: {e}"
            )
        return (apply_processor(image, proc),)


# ============================================================================
#  7.  ACESIOLogConvert  —  scene-linear ↔ compositing-log  (OCIOLogConvert)
# ============================================================================

class ACESIOLogConvert:
    """
    Convert between scene-linear and compositing-log colorspaces.
    Mirrors Nuke's OCIOLogConvert node.

    Uses the OCIO config's 'scene_linear' and 'compositing_log' roles
    (in ACES configs: ACEScg and ACEScct respectively).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":     ("IMAGE",),
                "ocio_config":("OCIO_CONFIG",),
                "operation": (["Log to Linear", "Linear to Log"], {"default": "Log to Linear"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION     = "convert"
    CATEGORY     = "ACES IO/Transform"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def convert(self, image, ocio_config, operation):
        cfg = ocio_config["config"]

        try:
            scene_linear    = cfg.getRoleColorSpace(ocio.ROLE_SCENE_LINEAR)
            compositing_log = cfg.getRoleColorSpace(ocio.ROLE_COMPOSITING_LOG)
        except ocio.Exception as e:
            raise ValueError(
                f"ACESIOLogConvert: config does not define 'scene_linear' and/or "
                f"'compositing_log' roles.\nOCIO error: {e}"
            )

        if operation == "Log to Linear":
            src, dst = compositing_log, scene_linear
        else:
            src, dst = scene_linear, compositing_log

        try:
            proc = cfg.getProcessor(src, dst)
        except ocio.Exception as e:
            raise ValueError(
                f"ACESIOLogConvert: cannot convert '{src}' → '{dst}'.\nOCIO error: {e}"
            )
        return (apply_processor(image, proc),)


# ============================================================================
#  8.  ACESIOInfo  —  list config contents  (utility)
# ============================================================================

class ACESIOInfo:
    """
    Inspect an OCIO config — list colorspaces, displays, views, looks, or roles.
    Connect its STRING output to a Note or text node to see what's available.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ocio_config": ("OCIO_CONFIG",),
                "list_type":   (["Colorspaces", "Displays + Views", "Looks",
                                  "Roles", "Config Info"],
                                {"default": "Colorspaces"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("info",)
    FUNCTION     = "get_info"
    CATEGORY     = "ACES IO/Utility"
    OUTPUT_NODE  = True

    def get_info(self, ocio_config, list_type):
        cfg    = ocio_config["config"]
        preset = ocio_config.get("preset", "?")
        lines  = [f"Config: {preset}", ""]

        if list_type == "Colorspaces":
            lines.append("=== Colorspaces ===")
            for name in get_colorspaces(cfg):
                lines.append(f"  {name}")

        elif list_type == "Displays + Views":
            lines.append("=== Displays / Views ===")
            for display in get_displays(cfg):
                lines.append(f"  [{display}]")
                for view in get_views(cfg, display):
                    lines.append(f"      {view}")

        elif list_type == "Looks":
            lines.append("=== Looks ===")
            for lk in cfg.getLooks():
                lines.append(f"  {lk.getName()}  (process_space: {lk.getProcessSpace()})")

        elif list_type == "Roles":
            lines.append("=== Roles ===")
            for role, cs in cfg.getRoles():
                lines.append(f"  {role}: {cs}")

        elif list_type == "Config Info":
            lines.append("=== Config Info ===")
            lines.append(f"  OCIO profile version: {cfg.getMajorVersion()}.{cfg.getMinorVersion()}")
            lines.append(f"  Num colorspaces: {cfg.getNumColorSpaces()}")
            lines.append(f"  Num looks:       {len(list(cfg.getLooks()))}")
            lines.append(f"  Num displays:    {len(get_displays(cfg))}")
            try:
                lines.append(f"  scene_linear role:    {cfg.getRoleColorSpace(ocio.ROLE_SCENE_LINEAR)}")
                lines.append(f"  compositing_log role: {cfg.getRoleColorSpace(ocio.ROLE_COMPOSITING_LOG)}")
                lines.append(f"  color_timing role:    {cfg.getRoleColorSpace(ocio.ROLE_COLOR_TIMING)}")
            except Exception:
                pass

        text = "\n".join(lines)
        print(text)        # also print to ComfyUI console
        return {"ui": {"text": [text]}, "result": (text,)}


# ============================================================================
#  9.  ACESIOEXRSaver  —  save IMAGE tensor as OpenEXR
# ============================================================================

class ACESIOEXRSaver:
    """
    Save a ComfyUI IMAGE tensor as an OpenEXR file.

    Supports full 16-bit half-float and 32-bit float with all standard
    EXR compression codecs (ZIP, PIZ, DWAA, …).

    output_dir   Directory to write into  (use the Browse button to pick one).
    filename     Base filename without extension; %04d is replaced by the
                 frame/batch index, e.g.  render_%04d  →  render_0001.exr
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":       ("IMAGE",),
                "output_dir":  ("ACES_PATH",  {"default": os.path.expanduser("~/"),
                                               "mode": "dir"}),
                "filename":    ("STRING",     {"default": "render_%04d",
                                               "multiline": False}),
                "bit_depth":   (BIT_DEPTHS,   {"default": BIT_DEPTHS[0]}),
                "compression": (COMPRESSION_KEYS,
                                {"default": COMPRESSION_KEYS[0]}),
            },
            "optional": {
                "start_frame": ("INT", {"default": 1, "min": 0, "max": 99999}),
            },
        }

    RETURN_TYPES  = ("IMAGE", "STRING")
    RETURN_NAMES  = ("image", "saved_path")
    FUNCTION      = "save"
    CATEGORY      = "ACES IO/EXR"
    OUTPUT_NODE   = True

    def save(self, image, output_dir, filename, bit_depth, compression,
             start_frame=1):
        B = image.shape[0]
        last_path = ""
        for b in range(B):
            frame_num  = start_frame + b
            base_name  = re.sub(r"%0(\d+)d", lambda m: f"{frame_num:0{m.group(1)}d}", filename)
            if not base_name.lower().endswith(".exr"):
                base_name += ".exr"
            path = os.path.join(output_dir.strip(), base_name)
            last_path = save_exr(image, path, bit_depth, compression, frame_index=b)
        return {"ui": {"text": [last_path]}, "result": (image, last_path)}


# ============================================================================
#  10. ACESIOEXRLoader  —  load an EXR file as IMAGE tensor
# ============================================================================

class ACESIOEXRLoader:
    """
    Load an OpenEXR file and output it as a float32 IMAGE tensor.

    The image is loaded as-is (no colorspace conversion).  Connect the
    output to an ACESIOColorSpace node if you need to convert from the
    file's colorspace to your working space.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("ACES_PATH", {"default": "",
                                             "mode": "file",
                                             "filter": ".exr"}),
            }
        }

    RETURN_TYPES  = ("IMAGE",)
    RETURN_NAMES  = ("image",)
    FUNCTION      = "load"
    CATEGORY      = "ACES IO/EXR"
    OUTPUT_NODE   = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def load(self, file_path):
        path = file_path.strip()
        if not path:
            raise ValueError("ACESIOEXRLoader: file_path is empty.")
        tensor = load_exr(path)
        # Clamp to [0,1] for the thumbnail preview only (EXR may be HDR)
        preview_tensor = tensor.clamp(0.0, 1.0)
        previews = _save_preview(preview_tensor)
        return {"ui": {"images": previews}, "result": (tensor,)}


# ============================================================================
#  11. ACESIOEXRViewer  —  HDR / EXR preview with OCIO tone-mapping
# ============================================================================

class ACESIOEXRViewer:
    """
    Convert a scene-linear / HDR image to a display-referred output for
    previewing in ComfyUI's image viewer.

    This is identical in principle to ACESIOViewer but is labelled
    separately so it's easy to find next to the EXR loader in the menu.
    Wire an EXR loaded image through this node to see it tone-mapped through
    the ACES Output Transform (or any other view you choose).

    Exposure / gamma controls mirror Nuke's viewer E and G knobs.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image":            ("IMAGE",),
                "ocio_config":      ("OCIO_CONFIG",),
                "input_colorspace": ("ACES_COLORSPACE", {"default": "ACEScg"}),
                "display":          ("ACES_DISPLAY",    {"default": "sRGB - Display"}),
                "view":             ("ACES_VIEW",        {"default": "ACES 2.0 - SDR 100 nits (Rec.709)"}),
                "exposure":         ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0,
                                               "step": 0.1,
                                               "tooltip": "Exposure in stops (scene-linear)"}),
                "gamma":            ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0,
                                               "step": 0.01,
                                               "tooltip": "Display-space gamma"}),
                "channel":          (["RGBA", "R", "G", "B", "A", "Luminance"],
                                     {"default": "RGBA"}),
            }
        }

    RETURN_TYPES  = ("IMAGE",)
    RETURN_NAMES  = ("image",)
    FUNCTION      = "preview"
    CATEGORY      = "ACES IO/EXR"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def preview(self, image, ocio_config, input_colorspace, display, view,
                exposure, gamma, channel):
        cfg = ocio_config["config"]

        dv = ocio.DisplayViewTransform()
        dv.setSrc(input_colorspace.strip())
        dv.setDisplay(display.strip())
        dv.setView(view.strip())

        pipeline = ocio.LegacyViewingPipeline()
        pipeline.setDisplayViewTransform(dv)

        exp_t = build_exposure_transform(exposure)
        if exp_t: pipeline.setLinearCC(exp_t)

        ch_t = build_channel_view_transform(channel)
        if ch_t: pipeline.setChannelView(ch_t)

        gam_t = build_gamma_transform(gamma)
        if gam_t: pipeline.setDisplayCC(gam_t)

        try:
            proc = pipeline.getProcessor(cfg)
        except ocio.Exception as e:
            raise ValueError(
                f"ACESIOEXRViewer: failed to build pipeline.\n"
                f"  input_colorspace = '{input_colorspace}'\n"
                f"  display          = '{display}'\n"
                f"  view             = '{view}'\n"
                f"OCIO error: {e}"
            )
        return (apply_processor(image, proc),)


# ============================================================================
#  12. ACESIODownloadACES12  —  download ACES 1.2 config on demand
# ============================================================================

class ACESIODownloadACES12:
    """
    Download the ACES 1.2 OpenColorIO config (~130 MB) from the
    colour-science GitHub releases and save it to:
        ComfyUI-ACES-IO/configs/aces_1.2/config.ocio

    After downloading, restart ComfyUI and connect an ACESIOConfig node —
    "ACES 1.2  (colour-science / OCIO v1)" will appear in the preset list.

    Connect the output to any node that accepts a STRING to see the status.
    Set trigger=True to start the download (change the value to re-trigger).
    """

    @classmethod
    def INPUT_TYPES(cls):
        from .ocio_utils import _ACES12_CFG
        already = os.path.isfile(_ACES12_CFG)
        return {
            "required": {
                "trigger": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Set to True to start the download.",
                }),
            }
        }

    RETURN_TYPES  = ("STRING",)
    RETURN_NAMES  = ("status",)
    FUNCTION      = "download"
    CATEGORY      = "ACES IO/Config"
    OUTPUT_NODE   = True

    def download(self, trigger: bool):
        from .ocio_utils import _ACES12_CFG, ACES12_DOWNLOAD_URL, _refresh_aces12, _CONFIGS_DIR
        import threading, urllib.request, zipfile, shutil

        if os.path.isfile(_ACES12_CFG):
            return ("ACES 1.2 already downloaded: " + _ACES12_CFG,)

        if not trigger:
            return ("Set trigger=True to start download (~130 MB).",)

        status_box = ["Downloading…"]

        def _do():
            tmp = os.path.join(_CONFIGS_DIR, "_aces12_tmp.zip")
            os.makedirs(_CONFIGS_DIR, exist_ok=True)
            try:
                with urllib.request.urlopen(ACES12_DOWNLOAD_URL, timeout=120) as r, \
                     open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)

                with zipfile.ZipFile(tmp, "r") as zf:
                    zf.extractall(_CONFIGS_DIR)
                    extracted = None
                    for name in zf.namelist():
                        top = name.split("/")[0]
                        if top and os.path.isdir(os.path.join(_CONFIGS_DIR, top)):
                            extracted = top
                            break
                    if extracted:
                        dest = os.path.join(_CONFIGS_DIR, "aces_1.2")
                        if os.path.isdir(dest):
                            shutil.rmtree(dest)
                        os.rename(os.path.join(_CONFIGS_DIR, extracted), dest)

                os.remove(tmp)
                _refresh_aces12()
                status_box[0] = "Done! Restart ComfyUI to use ACES 1.2."
            except Exception as exc:
                if os.path.isfile(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
                status_box[0] = f"Error: {exc}"

        t = threading.Thread(target=_do, daemon=True)
        t.start()
        t.join()   # block until done so we can return the final status
        return (status_box[0],)


# ============================================================================
#  13. ACESIOPreview  —  display an IMAGE tensor inline in the node
# ============================================================================

class ACESIOPreview:
    """
    Preview any IMAGE tensor directly inside the node — identical to
    ComfyUI's built-in PreviewImage but lives in the ACES IO menu so you
    can drop it anywhere in your colour-management chain.

    Pass-through: the image is forwarded unchanged so you can chain nodes.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",)}}

    RETURN_TYPES  = ("IMAGE",)
    RETURN_NAMES  = ("image",)
    FUNCTION      = "preview"
    CATEGORY      = "ACES IO"
    OUTPUT_NODE   = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def preview(self, image):
        previews = _save_preview(image)
        return {"ui": {"images": previews}, "result": (image,)}


# ============================================================================
#  Node registration
# ============================================================================

NODE_CLASS_MAPPINGS = {
    "ACESIOConfig":      ACESIOConfig,
    "ACESIOColorSpace":  ACESIOColorSpace,
    "ACESIODisplay":     ACESIODisplay,
    "ACESIOViewer":      ACESIOViewer,
    "ACESIOLook":        ACESIOLook,
    "ACESIOFileLUT":     ACESIOFileLUT,
    "ACESIOLogConvert":  ACESIOLogConvert,
    "ACESIOInfo":        ACESIOInfo,
    "ACESIOEXRSaver":    ACESIOEXRSaver,
    "ACESIOEXRLoader":   ACESIOEXRLoader,
    "ACESIOEXRViewer":        ACESIOEXRViewer,
    "ACESIODownloadACES12":   ACESIODownloadACES12,
    "ACESIOPreview":          ACESIOPreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ACESIOConfig":      "ACES IO — Config Loader",
    "ACESIOColorSpace":  "ACES IO — ColorSpace  (OCIOColorSpace)",
    "ACESIODisplay":     "ACES IO — Display Transform  (OCIODisplay)",
    "ACESIOViewer":      "ACES IO — Viewer  (Nuke Viewer)",
    "ACESIOLook":        "ACES IO — Look Transform  (OCIOLookTransform)",
    "ACESIOFileLUT":     "ACES IO — File LUT  (OCIOFileTransform)",
    "ACESIOLogConvert":  "ACES IO — Log Convert  (OCIOLogConvert)",
    "ACESIOInfo":        "ACES IO — Config Info",
    "ACESIOEXRSaver":    "ACES IO — EXR Saver",
    "ACESIOEXRLoader":   "ACES IO — EXR Loader",
    "ACESIOEXRViewer":        "ACES IO — EXR Viewer  (HDR preview)",
    "ACESIODownloadACES12":   "ACES IO — Download ACES 1.2 Config",
    "ACESIOPreview":          "ACES IO — Preview",
}
