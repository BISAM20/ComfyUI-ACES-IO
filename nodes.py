"""
ComfyUI-ACES-IO  —  OpenColorIO / ACES color-management nodes.

Mirrors Nuke's OCIO node set exactly:
  ACESIOConfig          ≈  Project Settings → OCIO config
  ACESIOColorSpace      ≈  OCIOColorSpace node
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
try:
    import PyOpenColorIO as ocio
except ImportError as _e:
    raise ImportError(
        "[ACES IO] PyOpenColorIO is not installed.\n"
        "Run:  pip install opencolorio>=2.3.0\n"
        "  or: conda install -c conda-forge opencolorio>=2.3.0"
    ) from _e
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


def _tensor_to_pil_frames(tensor: torch.Tensor) -> list:
    """Convert a [B, H, W, C] float32 tensor to a list of PIL Images (uint8)."""
    frames = []
    for i in range(tensor.shape[0]):
        frame = tensor[i].cpu().float().numpy()
        frame = (frame * 255.0).clip(0, 255).astype(np.uint8)
        C = frame.shape[2]
        if C == 1:
            frames.append(Image.fromarray(frame[:, :, 0], mode="L").convert("RGB"))
        elif C == 4:
            frames.append(Image.fromarray(frame, mode="RGBA"))
        else:
            frames.append(Image.fromarray(frame[:, :, :3], mode="RGB"))
    return frames


def _save_preview(tensor: torch.Tensor) -> list:
    """
    Save a [B,H,W,C] float32 IMAGE tensor to ComfyUI's temp folder as PNG.
    Returns the list of image dicts expected by ComfyUI's UI preview system.
    """
    temp_dir = folder_paths.get_temp_directory()
    os.makedirs(temp_dir, exist_ok=True)
    results = []
    for img in _tensor_to_pil_frames(tensor):
        filename = f"aces_io_preview_{uuid.uuid4().hex[:12]}.png"
        img.save(os.path.join(temp_dir, filename))
        results.append({"filename": filename, "subfolder": "", "type": "temp"})
    return results


def _save_animated_preview(tensor: torch.Tensor, fps: float = 24.0) -> list:
    """
    Save a [B,H,W,C] tensor to ComfyUI's temp folder.

    Single frame  → PNG  (same as _save_preview)
    Multi-frame   → animated WebP  (ComfyUI's frontend plays it natively)

    Returns the list of image dicts for ComfyUI's UI preview system.
    """
    temp_dir = folder_paths.get_temp_directory()
    os.makedirs(temp_dir, exist_ok=True)
    frames = _tensor_to_pil_frames(tensor)

    if len(frames) == 1:
        filename = f"aces_io_preview_{uuid.uuid4().hex[:12]}.png"
        frames[0].save(os.path.join(temp_dir, filename))
        return [{"filename": filename, "subfolder": "", "type": "temp"}]

    duration_ms = max(1, int(1000.0 / fps))
    filename = f"aces_io_preview_{uuid.uuid4().hex[:12]}.webp"
    path = os.path.join(temp_dir, filename)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
    )
    return [{"filename": filename, "subfolder": "", "type": "temp"}]


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
#  Helpers — Nuke-style sequence detection & loading
# ============================================================================

def _detect_exr_sequence(path: str):
    """
    Nuke-style sequence auto-detection (mirrors nuke.getFileNameList logic).

    Handles ALL common VFX naming conventions:
      render.####.exr          Nuke hash notation
      render.%04d.exr          printf notation
      render.0001.exr          dot-separated frame  (any padding)
      render_0001.exr          underscore-separated frame
      render-0001.exr          hyphen-separated frame
      0001.exr                 frame-only name
      ~/path/render.0001.exr   tilde expansion
      /dir with [brackets]/    glob-safe directory escaping

    Returns (template, sorted_frame_list) or (path, None) for plain files.
    template is always a printf-style absolute path.
    """
    import glob as _glob

    # Expand ~ and normalise to absolute path
    path    = os.path.expanduser(path.strip())
    dirpath = os.path.dirname(os.path.abspath(path))
    bname   = os.path.basename(path)

    # ── 1. Already a pattern?  #### or %04d ──────────────────────────────────
    hash_m   = re.search(r'(#+)', bname)
    printf_m = re.search(r'(%0*\d*d)', bname)

    if hash_m:
        pad      = len(hash_m.group(1))
        template = os.path.join(dirpath,
                                re.sub(r'#+', f'%0{pad}d', bname, count=1))
        glob_pat = os.path.join(_glob.escape(dirpath),
                                re.sub(r'#+', '*',          bname, count=1))

    elif printf_m:
        template = os.path.join(dirpath, bname)
        glob_pat = os.path.join(_glob.escape(dirpath),
                                re.sub(r'%0*\d*d', '*',    bname, count=1))

    else:
        # ── 2. Concrete file → locate the frame number ───────────────────────
        # Split off extension: "render_0001", ".exr"
        root, ext = os.path.splitext(bname)

        # Find every digit group in the stem; use the LAST one as frame number.
        # This correctly handles v01 prefix tokens: shot_v01_beauty_0042 → 0042
        digit_ms = list(re.finditer(r'\d+', root))
        if not digit_ms:
            # No digits at all → genuinely a single file
            return path, None

        last_m  = digit_ms[-1]
        pad     = len(last_m.group())
        prefix  = root[:last_m.start()]   # e.g. "render_", "render.", "shot_v01_"
        suffix  = root[last_m.end():]     # anything after the digits (usually empty)

        template = os.path.join(dirpath,
                                f'{prefix}%0{pad}d{suffix}{ext}')
        # Escape fixed parts so brackets/parens in dir/prefix don't break glob
        glob_pat = os.path.join(
            _glob.escape(dirpath),
            f'{_glob.escape(prefix)}*{_glob.escape(suffix)}{_glob.escape(ext)}'
        )

    # ── 3. Build frame-extraction regex from the template ────────────────────
    tmpl_bname = os.path.basename(template)
    fmt_m      = re.search(r'%0*\d*d', tmpl_bname)
    if fmt_m:
        frame_re = re.compile(
            r'^'
            + re.escape(tmpl_bname[:fmt_m.start()])
            + r'(\d+)'
            + re.escape(tmpl_bname[fmt_m.end():])
            + r'$',
            re.IGNORECASE,
        )
    else:
        frame_re = None   # shouldn't happen, but handled below

    # ── 4. Scan disk ─────────────────────────────────────────────────────────
    try:
        files = sorted(_glob.glob(glob_pat))
    except Exception as exc:
        print(f"[ACES IO] Glob error: {exc}  →  {glob_pat}")
        return path, None

    frames = []
    for f in files:
        bn = os.path.basename(f)
        if frame_re:
            m = frame_re.match(bn)
            if m:
                frames.append(int(m.group(1)))
        else:
            # Fallback: last digit group in stem
            r2, _ = os.path.splitext(bn)
            ms = list(re.finditer(r'\d+', r2))
            if ms:
                frames.append(int(ms[-1].group()))

    if not frames:
        print(f"[ACES IO] No sequence found — glob: {glob_pat}")
        return path, None

    unique_frames = sorted(set(frames))
    print(f"[ACES IO] Sequence detected: {tmpl_bname}  "
          f"{unique_frames[0]}–{unique_frames[-1]}  ({len(unique_frames)} frames)")
    return template, unique_frames


def _load_seq(template, frame_list, frame_set, missing_frames, ref_shape_holder):
    """
    Load a list of frame numbers from a printf template.

    missing_frames:
      "error"  → raise FileNotFoundError on any missing frame
      "black"  → substitute a zero tensor of the same shape
      "hold"   → repeat the most recent successfully loaded frame
                 (if no frame loaded yet, hold the next available one instead)
    """
    tensors   = []
    last_good = None

    for i in frame_list:
        if i in frame_set:
            t         = load_exr(template % i)
            last_good = t
            if not ref_shape_holder:
                ref_shape_holder.append(t.shape[1:])   # store (H, W, C)
            tensors.append(t)
        else:
            if missing_frames == "error":
                raise FileNotFoundError(
                    f"EXR Loader: frame {i} is missing.  "
                    f"Available: {min(frame_set)}–{max(frame_set)}"
                )
            # Need reference shape for black / hold fallback
            if not ref_shape_holder:
                first_avail = min(frame_set)
                ref        = load_exr(template % first_avail)
                ref_shape_holder.append(ref.shape[1:])
            H, W, C = ref_shape_holder[0]

            if missing_frames == "black":
                tensors.append(torch.zeros(1, H, W, C))
            else:  # "hold"
                if last_good is not None:
                    tensors.append(last_good)
                else:
                    tensors.append(torch.zeros(1, H, W, C))

    return torch.cat(tensors, dim=0)   # [B, H, W, C]


# ============================================================================
#  10. ACESIOEXRLoader  —  Nuke Read node equivalent
# ============================================================================

class ACESIOEXRLoader:
    """
    Load a single EXR or an EXR sequence — mirrors Nuke's Read node.

    file_path
    ─────────
    Point at ANY frame of a sequence, a #### / %04d pattern, or a plain file.
    The node scans the folder automatically to find all available frames
    (identical to how Nuke's Read node works).

    frame_mode
    ──────────
    all     Load every frame found on disk.  first / last are read-only info.
    range   Load first_frame … last_frame inclusive.  Set both manually.
    single  Load exactly one frame, specified by first_frame.

    missing_frames
    ──────────────
    error   Abort with an exception (default, matches Nuke behaviour).
    black   Substitute a black frame for any missing frame.
    hold    Repeat the last successfully loaded frame.

    Outputs: image  [B, H, W, C] · frame_count · first_frame · last_frame
    """

    FRAME_MODES     = ["all", "range", "single"]
    MISSING_OPTIONS = ["error", "black", "hold"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("ACES_PATH", {
                    "default": "",
                    "mode":    "file",
                    "filter":  ".exr",
                }),
                "frame_mode": (cls.FRAME_MODES, {"default": "all"}),
            },
            "optional": {
                "first_frame": ("INT", {
                    "default": 1001, "min": 0, "max": 999999,
                    "tooltip": "Used by 'range' and 'single' modes",
                }),
                "last_frame": ("INT", {
                    "default": 1001, "min": 0, "max": 999999,
                    "tooltip": "Used by 'range' mode",
                }),
                "missing_frames": (cls.MISSING_OPTIONS, {"default": "error"}),
                "preview_fps": ("FLOAT", {
                    "default": 24.0, "min": 1.0, "max": 120.0, "step": 0.5,
                    "tooltip": "Animated preview playback speed",
                }),
            },
        }

    RETURN_TYPES  = ("IMAGE", "INT", "INT", "INT")
    RETURN_NAMES  = ("image", "frame_count", "first_frame", "last_frame")
    FUNCTION      = "load"
    CATEGORY      = "ACES IO/EXR"
    OUTPUT_NODE   = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def load(self, file_path,
             frame_mode="all",
             first_frame=1001, last_frame=1001,
             missing_frames="error",
             preview_fps=24.0):

        path = os.path.expanduser(file_path.strip())
        if not path:
            raise ValueError("EXR Loader: file_path is empty.")

        template, detected = _detect_exr_sequence(path)

        # ── single plain file (no sequence detected) ──────────────────────
        if detected is None:
            tensor      = load_exr(path)
            out_first   = out_last = 0
            print(f"[ACES IO] EXR Loader: single file  {path}")

        # ── sequence ──────────────────────────────────────────────────────
        else:
            disk_first, disk_last = detected[0], detected[-1]
            frame_set             = set(detected)

            if frame_mode == "all":
                frames_to_load = detected           # every frame on disk
                out_first, out_last = disk_first, disk_last

            elif frame_mode == "range":
                if last_frame < first_frame:
                    raise ValueError(
                        f"EXR Loader: last_frame ({last_frame}) < first_frame ({first_frame})."
                    )
                frames_to_load = list(range(first_frame, last_frame + 1))
                out_first, out_last = first_frame, last_frame

            else:  # "single"
                frames_to_load = [first_frame]
                out_first = out_last = first_frame

            ref_shape: list = []
            tensor = _load_seq(template, frames_to_load, frame_set,
                               missing_frames, ref_shape)

            print(f"[ACES IO] EXR Loader: {frame_mode}  "
                  f"{out_first}–{out_last}  ({tensor.shape[0]} frames)  "
                  f"disk: {disk_first}–{disk_last}")

        frame_count    = tensor.shape[0]
        preview_tensor = tensor.clamp(0.0, 1.0)
        previews       = _save_animated_preview(preview_tensor, fps=preview_fps)
        return {
            "ui":     {"images": previews},
            "result": (tensor, frame_count, out_first, out_last),
        }


# ============================================================================
#  11. ACESIOPreview  —  display an IMAGE tensor inline in the node
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
#  12. ACESIOVideoSaver  —  export an IMAGE batch as a video / animated file
# ============================================================================

class ACESIOVideoSaver:
    """
    Export a ComfyUI IMAGE batch (e.g. from the EXR Loader) to a video file.

    Formats
    ───────
    MP4 (H.264)      Standard video via OpenCV — plays in any media player.
    Animated WebP    High-quality lossless/near-lossless, plays in browsers and
                     most modern viewers.  Best for round-tripping back to ComfyUI.
    Animated GIF     Universal compatibility; limited to 256 colours.

    output_path
        Full path including filename.  The correct extension is appended
        automatically if missing (.mp4 / .webp / .gif).

    The node passes the IMAGE tensor through unchanged so it can sit inline
    in any graph without interrupting the flow.
    """

    FORMATS = ["MP4 (H.264)", "Animated WebP", "Animated GIF"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "output_path": ("ACES_PATH", {
                    "default": os.path.expanduser("~/output.mp4"),
                    "mode":    "file",
                    "placeholder": "/path/to/output.mp4  (.mp4 / .webp / .gif)",
                }),
                "format": (cls.FORMATS, {"default": "MP4 (H.264)"}),
                "fps":    ("FLOAT", {
                    "default": 24.0, "min": 1.0, "max": 120.0, "step": 0.5,
                    "tooltip": "Frames per second",
                }),
            },
        }

    RETURN_TYPES  = ("IMAGE", "STRING")
    RETURN_NAMES  = ("images", "saved_path")
    FUNCTION      = "save_video"
    CATEGORY      = "ACES IO/EXR"
    OUTPUT_NODE   = True

    def save_video(self, images, output_path, format, fps):
        path = output_path.strip()
        if not path:
            raise ValueError("ACESIOVideoSaver: output_path is empty.")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        if format == "MP4 (H.264)":
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            _write_mp4(images, path, fps)
        elif format == "Animated WebP":
            if not path.lower().endswith(".webp"):
                path += ".webp"
            _write_webp(images, path, fps)
        elif format == "Animated GIF":
            if not path.lower().endswith(".gif"):
                path += ".gif"
            _write_gif(images, path, fps)

        B = images.shape[0]
        print(f"[ACES IO] VideoSaver: wrote {B} frames → '{path}'")
        return {"ui": {"text": [path]}, "result": (images, path)}


# ── video-writing helpers ────────────────────────────────────────────────────

def _write_webp(tensor: torch.Tensor, path: str, fps: float):
    frames = _tensor_to_pil_frames(tensor)
    duration_ms = max(1, int(1000.0 / fps))
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
    )


def _write_gif(tensor: torch.Tensor, path: str, fps: float):
    frames = _tensor_to_pil_frames(tensor)
    # Quantise to 256-colour palette for GIF
    palette_frames = [f.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                      for f in frames]
    duration_ms = max(1, int(1000.0 / fps))
    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
    )


def _write_mp4(tensor: torch.Tensor, path: str, fps: float):
    try:
        import cv2
    except ImportError:
        raise ImportError(
            "ACESIOVideoSaver: OpenCV (cv2) is required for MP4 export.\n"
            "Install with:  pip install opencv-python"
        )
    B, H, W, C = tensor.shape
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, float(fps), (W, H))
    if not writer.isOpened():
        raise IOError(f"ACESIOVideoSaver: could not open video writer for '{path}'")
    for i in range(B):
        frame = tensor[i].cpu().float().numpy()
        frame = (frame * 255.0).clip(0, 255).astype(np.uint8)
        bgr   = frame[:, :, [2, 1, 0]] if C >= 3 else np.repeat(frame, 3, axis=2)
        writer.write(bgr)
    writer.release()


# ============================================================================
#  Node registration
# ============================================================================

NODE_CLASS_MAPPINGS = {
    "ACESIOConfig":       ACESIOConfig,
    "ACESIOColorSpace":   ACESIOColorSpace,
    "ACESIOViewer":       ACESIOViewer,
    "ACESIOLook":         ACESIOLook,
    "ACESIOFileLUT":      ACESIOFileLUT,
    "ACESIOLogConvert":   ACESIOLogConvert,
    "ACESIOInfo":         ACESIOInfo,
    "ACESIOEXRSaver":     ACESIOEXRSaver,
    "ACESIOEXRLoader":    ACESIOEXRLoader,
    "ACESIOVideoSaver":   ACESIOVideoSaver,
    "ACESIOPreview":      ACESIOPreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ACESIOConfig":       "ACES IO — Config Loader",
    "ACESIOColorSpace":   "ACES IO — ColorSpace  (OCIOColorSpace)",
    "ACESIOViewer":       "ACES IO — Viewer  (Nuke Viewer)",
    "ACESIOLook":         "ACES IO — Look Transform  (OCIOLookTransform)",
    "ACESIOFileLUT":      "ACES IO — File LUT  (OCIOFileTransform)",
    "ACESIOLogConvert":   "ACES IO — Log Convert  (OCIOLogConvert)",
    "ACESIOInfo":         "ACES IO — Config Info",
    "ACESIOEXRSaver":     "ACES IO — EXR Saver",
    "ACESIOEXRLoader":    "ACES IO — EXR Loader",
    "ACESIOVideoSaver":   "ACES IO — Video Saver",
    "ACESIOPreview":      "ACES IO — Preview",
}
