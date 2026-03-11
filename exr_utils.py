"""
EXR read/write helpers using OpenEXR + Imath.
Falls back to cv2 if OpenEXR is unavailable.
"""

import os
import numpy as np
import torch

# Must be set before cv2 is imported, otherwise OpenEXR support stays disabled.
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

try:
    import OpenEXR
    import Imath
    _HAVE_OPENEXR = True
except ImportError:
    _HAVE_OPENEXR = False

try:
    import cv2 as _cv2
    _HAVE_CV2 = True
except ImportError:
    _HAVE_CV2 = False

# ── compression name → Imath constant ────────────────────────────────────────
COMPRESSIONS = {
    "ZIP  (lossless, recommended)":  "ZIP_COMPRESSION",
    "ZIPS (lossless, scanline)":     "ZIPS_COMPRESSION",
    "PIZ  (lossless, wavelet)":      "PIZ_COMPRESSION",
    "PXR24 (lossy, 24-bit)":         "PXR24_COMPRESSION",
    "RLE  (lossless, run-length)":   "RLE_COMPRESSION",
    "B44  (lossy, fixed ratio)":     "B44_COMPRESSION",
    "DWAA (lossy, DCT, fast)":       "DWAA_COMPRESSION",
    "None (uncompressed)":           "NO_COMPRESSION",
}
COMPRESSION_KEYS = list(COMPRESSIONS.keys())

BIT_DEPTHS = ["16f (half-float)", "32f (float)"]


def save_exr(
    tensor: torch.Tensor,
    path: str,
    bit_depth: str = "16f (half-float)",
    compression: str = "ZIP  (lossless, recommended)",
    frame_index: int = 0,
) -> str:
    """
    Save one frame from a [B, H, W, C] tensor as an OpenEXR file.
    Returns the path actually written.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    img = tensor[frame_index].cpu().float().numpy()   # [H, W, C]
    H, W, C = img.shape
    use_half = "16f" in bit_depth

    if _HAVE_OPENEXR:
        _save_exr_openexr(img, path, H, W, C, use_half, compression)
    elif _HAVE_CV2:
        _save_exr_cv2(img, path, use_half)
    else:
        raise ImportError(
            "Neither OpenEXR nor cv2 is available. "
            "Install with:  pip install openexr  or  pip install opencv-python"
        )
    return path


def _save_exr_openexr(img, path, H, W, C, use_half, compression_key):
    comp_name = COMPRESSIONS.get(compression_key, "ZIP_COMPRESSION")
    imath_comp = getattr(Imath.Compression, comp_name)
    ptype_write = Imath.PixelType(Imath.PixelType.HALF if use_half else Imath.PixelType.FLOAT)
    dtype_write = np.float16 if use_half else np.float32

    channel_names = ["R", "G", "B", "A"] if C == 4 else ["R", "G", "B"]

    header = OpenEXR.Header(W, H)
    header["compression"] = Imath.Compression(imath_comp)
    header["channels"] = {ch: Imath.Channel(ptype_write) for ch in channel_names}

    out = OpenEXR.OutputFile(path, header)
    pixels = {}
    for i, ch in enumerate(channel_names):
        pixels[ch] = img[:, :, i].astype(dtype_write).tobytes()
    out.writePixels(pixels)
    out.close()


def _save_exr_cv2(img, path, use_half):
    import cv2
    # cv2 uses BGR order and float32 only
    if img.shape[2] == 3:
        out_img = img[:, :, ::-1].astype(np.float32)           # RGB→BGR
    elif img.shape[2] == 4:
        out_img = img[:, :, [2, 1, 0, 3]].astype(np.float32)  # RGBA→BGRA
    else:
        out_img = img.astype(np.float32)
    cv2.imwrite(path, out_img)


def load_exr(path: str) -> torch.Tensor:
    """
    Load an EXR file and return a [1, H, W, C] float32 tensor.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"EXR file not found: '{path}'")

    if _HAVE_OPENEXR:
        return _load_exr_openexr(path)
    elif _HAVE_CV2:
        return _load_exr_cv2(path)
    else:
        raise ImportError("Neither OpenEXR nor cv2 is available.")


def _load_exr_openexr(path: str) -> torch.Tensor:
    f = OpenEXR.InputFile(path)
    dw = f.header()["dataWindow"]
    W = dw.max.x - dw.min.x + 1
    H = dw.max.y - dw.min.y + 1
    PT = Imath.PixelType(Imath.PixelType.FLOAT)

    channels = list(f.header().get("channels", {}).keys())
    # Prefer RGBA order; accept any available channels
    ordered = []
    for ch in ["R", "G", "B", "A"]:
        if ch in channels:
            ordered.append(ch)
    if not ordered:
        ordered = channels[:4]

    arrays = []
    for ch in ordered:
        raw = f.channel(ch, PT)
        arrays.append(np.frombuffer(raw, dtype=np.float32).reshape(H, W))
    img = np.stack(arrays, axis=-1)   # [H, W, C]
    return torch.from_numpy(img).unsqueeze(0)  # [1, H, W, C]


def _load_exr_cv2(path: str) -> torch.Tensor:
    import cv2
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
    if img is None:
        raise IOError(f"cv2 could not read '{path}'")
    img = img.astype(np.float32)
    if img.ndim == 2:
        img = img[:, :, np.newaxis]
    elif img.shape[2] == 3:
        img = img[:, :, ::-1].copy()    # BGR→RGB
    elif img.shape[2] == 4:
        img = img[:, :, [2, 1, 0, 3]].copy()  # BGRA→RGBA
    return torch.from_numpy(img).unsqueeze(0)
