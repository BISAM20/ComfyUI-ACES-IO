"""
REST endpoints for ACES IO — serves colorspace / display / view data to the frontend.
"""

import os
import threading
import logging

from server import PromptServer
from aiohttp import web
from .ocio_utils import (
    load_config, BUILTIN_CONFIGS, _refresh_aces12,
    _CONFIGS_DIR, _ACES12_CFG, ACES12_DOWNLOAD_URL, ACES12_DOWNLOAD_SIZE,
)
try:
    import PyOpenColorIO as ocio
except ImportError as _e:
    raise ImportError(
        "[ACES IO] PyOpenColorIO is not installed.\n"
        "Run:  pip install opencolorio>=2.3.0\n"
        "  or: conda install -c conda-forge opencolorio>=2.3.0"
    ) from _e

logger = logging.getLogger(__name__)
routes = PromptServer.instance.routes

# ── ACES 1.2 download state ──────────────────────────────────────────────────
_dl_state = {"running": False, "progress": 0.0, "done": False, "error": None}


def _families_from_config(cfg: ocio.Config) -> dict:
    """Build {family: [cs_name, ...]} from an OCIO config."""
    families: dict = {}
    for cs in cfg.getColorSpaces():
        fam  = cs.getFamily().strip() if cs.getFamily() else "Other"
        name = cs.getName()
        families.setdefault(fam, []).append(name)
    return families


@routes.get("/aces_io/all_colorspaces")
async def all_colorspaces(request):
    """
    Return colorspace data for every built-in config.
    Response schema:
    {
        "config_names": ["ACES 2.0 CG [Recommended]", ...],
        "by_config": {
            "ACES 2.0 CG [Recommended]": {
                "families": { "ACES": [...], "Display": [...], ... }
            },
            ...
        }
    }
    """
    by_config: dict = {}
    for preset, builtin in BUILTIN_CONFIGS.items():
        if builtin == "__custom__":
            continue
        try:
            cfg = load_config(preset)
            by_config[preset] = {"families": _families_from_config(cfg)}
        except Exception as exc:
            by_config[preset] = {"error": str(exc)}

    return web.json_response({
        "config_names": [k for k, v in BUILTIN_CONFIGS.items() if v != "__custom__"],
        "by_config": by_config,
    })


@routes.get("/aces_io/colorspaces")
async def colorspaces_for_preset(request):
    """
    Return colorspaces for a single preset.
    Query params: preset, custom_path
    """
    preset      = request.rel_url.query.get("preset", "ACES 2.0 CG  [Recommended]")
    custom_path = request.rel_url.query.get("custom_path", "")
    try:
        cfg = load_config(preset, custom_path)
        return web.json_response({
            "preset":   preset,
            "families": _families_from_config(cfg),
        })
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)


@routes.get("/aces_io/displays_views")
async def displays_views(request):
    """
    Return all (display, [views]) pairs for a preset.
    Query params: preset, custom_path
    """
    preset      = request.rel_url.query.get("preset", "ACES 2.0 CG  [Recommended]")
    custom_path = request.rel_url.query.get("custom_path", "")
    try:
        cfg = load_config(preset, custom_path)
        data: dict = {}
        for display in cfg.getDisplays():
            data[display] = list(cfg.getViews(display))
        return web.json_response({"displays": data})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)


@routes.get("/aces_io/looks")
async def looks_for_preset(request):
    preset      = request.rel_url.query.get("preset", "ACES 2.0 CG  [Recommended]")
    custom_path = request.rel_url.query.get("custom_path", "")
    try:
        cfg   = load_config(preset, custom_path)
        looks = [lk.getName() for lk in cfg.getLooks()]
        return web.json_response({"looks": looks})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)


# ─────────────────────────────────────────────────────────────────────────────
#  File / directory browser
# ─────────────────────────────────────────────────────────────────────────────

@routes.get("/aces_io/browse")
async def browse(request):
    """
    Return directory listing for a path.
    Query params:
      path  — directory to list (defaults to user home)
      mode  — "file" | "dir"  (what to show)
      filter — file extension filter, e.g. ".exr" (only for mode=file)
    Response:
      { "path": "/abs/path", "parent": "/abs", "entries": [
          {"name": "foo", "type": "dir"},
          {"name": "bar.exr", "type": "file"} ] }
    """
    raw    = request.rel_url.query.get("path", "").strip()
    mode   = request.rel_url.query.get("mode", "file")
    filt   = request.rel_url.query.get("filter", "").lower()

    path = os.path.abspath(os.path.expanduser(raw)) if raw else os.path.expanduser("~")
    # If it's a file, go up to its parent
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if not os.path.isdir(path):
        path = os.path.expanduser("~")

    parent = os.path.dirname(path)

    entries = []
    try:
        with os.scandir(path) as it:
            for entry in sorted(it, key=lambda e: (not e.is_dir(), e.name.lower())):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    entries.append({"name": entry.name, "type": "dir"})
                elif mode == "file" and entry.is_file(follow_symlinks=False):
                    if not filt or entry.name.lower().endswith(filt):
                        entries.append({"name": entry.name, "type": "file"})
    except PermissionError:
        pass

    return web.json_response({"path": path, "parent": parent, "entries": entries})


# ─────────────────────────────────────────────────────────────────────────────
#  ACES 1.2 download
# ─────────────────────────────────────────────────────────────────────────────

def _do_download():
    """Background thread: download + unzip ACES 1.2 config."""
    import urllib.request, zipfile, shutil

    _dl_state.update(running=True, progress=0.0, done=False, error=None)
    tmp_zip = None
    try:
        tmp_zip = os.path.join(_CONFIGS_DIR, "_aces12_tmp.zip")
        os.makedirs(_CONFIGS_DIR, exist_ok=True)

        total = ACES12_DOWNLOAD_SIZE
        downloaded = 0
        with urllib.request.urlopen(ACES12_DOWNLOAD_URL, timeout=60) as resp, \
             open(tmp_zip, "wb") as fout:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                fout.write(chunk)
                downloaded += len(chunk)
                _dl_state["progress"] = min(downloaded / total, 0.95)

        _dl_state["progress"] = 0.97
        # Unzip into configs/
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            # The zip contains OpenColorIO-Config-ACES-1.2/aces.ocio …
            zf.extractall(_CONFIGS_DIR)
            # Rename extracted folder to aces_1.2
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

        os.remove(tmp_zip)
        _refresh_aces12()
        _dl_state.update(running=False, progress=1.0, done=True, error=None)
        logger.info("[ACES IO] ACES 1.2 config downloaded successfully.")
    except Exception as exc:
        if tmp_zip and os.path.isfile(tmp_zip):
            try: os.remove(tmp_zip)
            except: pass
        _dl_state.update(running=False, progress=0.0, done=False, error=str(exc))
        logger.error(f"[ACES IO] ACES 1.2 download failed: {exc}")


@routes.get("/aces_io/download_aces12")
async def download_aces12(request):
    """Start ACES 1.2 download in background and return current state."""
    if os.path.isfile(_ACES12_CFG):
        return web.json_response({"status": "already_downloaded"})
    if _dl_state["running"]:
        return web.json_response({
            "status":   "downloading",
            "progress": _dl_state["progress"],
        })
    # Start background download
    t = threading.Thread(target=_do_download, daemon=True)
    t.start()
    return web.json_response({"status": "started", "progress": 0.0})


@routes.get("/aces_io/download_aces12_status")
async def download_aces12_status(request):
    """Poll download progress."""
    if os.path.isfile(_ACES12_CFG):
        return web.json_response({"status": "done", "progress": 1.0})
    if _dl_state["error"]:
        return web.json_response({"status": "error", "error": _dl_state["error"]})
    if _dl_state["done"]:
        return web.json_response({"status": "done", "progress": 1.0})
    if _dl_state["running"]:
        return web.json_response({"status": "downloading", "progress": _dl_state["progress"]})
    return web.json_response({"status": "idle"})
