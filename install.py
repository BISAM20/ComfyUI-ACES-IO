"""
ComfyUI-ACES-IO — dependency installer
Runs automatically when installed via ComfyUI Manager.

PyOpenColorIO is NOT on PyPI, so we try multiple installation paths:
  1. Already importable  → skip
  2. pip install opencolorio  (community wheels on some platforms)
  3. conda / mamba install -c conda-forge opencolorio
  4. System package already on PYTHONPATH  (e.g. VFX apps, DCC environments)
  5. Print clear manual-install instructions and continue anyway
     (the node will show a helpful error at runtime rather than crashing ComfyUI)
"""

import subprocess
import sys
import shutil
import importlib.util
import os
import urllib.request
import zipfile
import tempfile


def _pip(*args):
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", *args],
        capture_output=True,
    ).returncode


def _conda_exec():
    for name in ("mamba", "micromamba", "conda"):
        path = shutil.which(name)
        if path:
            return path
    return None


def try_install_ocio() -> bool:
    # 1. Already available?
    if importlib.util.find_spec("PyOpenColorIO") is not None:
        print("[ACES IO] PyOpenColorIO already installed — OK")
        return True

    print("[ACES IO] PyOpenColorIO not found, attempting installation …")

    # 2. pip: the 'opencolorio' package provides PyOpenColorIO wheels
    #    on Linux/macOS/Windows for CPython 3.9–3.12
    if _pip("opencolorio>=2.3.0") == 0:
        if importlib.util.find_spec("PyOpenColorIO") is not None:
            print("[ACES IO] Installed PyOpenColorIO via pip (opencolorio package) — OK")
            return True

    # 3. conda / mamba
    conda = _conda_exec()
    if conda:
        print(f"[ACES IO] Trying {conda} install …")
        ret = subprocess.run(
            [conda, "install", "-y", "-c", "conda-forge", "opencolorio>=2.3.0"],
            capture_output=True,
        ).returncode
        if ret == 0 and importlib.util.find_spec("PyOpenColorIO") is not None:
            print("[ACES IO] Installed PyOpenColorIO via conda-forge — OK")
            return True

    # 4. Not found — print guidance but do NOT exit with an error code so that
    #    ComfyUI Manager still installs the other dependencies and marks the
    #    node as installed.  The node itself will show a clear error at runtime.
    print(
        "\n"
        "╔══════════════════════════════════════════════════════════════════╗\n"
        "║  [ACES IO] Could not auto-install PyOpenColorIO                 ║\n"
        "║                                                                  ║\n"
        "║  Please install it manually with ONE of:                         ║\n"
        "║                                                                  ║\n"
        "║  conda:   conda install -c conda-forge opencolorio>=2.3.0       ║\n"
        "║  mamba:   mamba install -c conda-forge opencolorio>=2.3.0       ║\n"
        "║  pip:     pip install opencolorio>=2.3.0                        ║\n"
        "║                                                                  ║\n"
        "║  Then restart ComfyUI.                                           ║\n"
        "╚══════════════════════════════════════════════════════════════════╝\n"
    )
    return False


def install_pip_deps():
    deps = ["numpy", "Pillow", "opencv-python", "openexr", "av"]
    if _pip(*deps) != 0:
        print(f"[ACES IO] Warning: could not install one or more of {deps}")


def download_aces12():
    """
    Auto-download and extract the ACES 1.2 OpenColorIO config if not already present.
    Downloads from the colour-science OpenColorIO-Configs GitHub release.
    Does NOT raise on error — installation continues regardless.
    """
    _HERE = os.path.dirname(os.path.abspath(__file__))
    dest_dir = os.path.join(_HERE, "configs", "aces_1.2")
    config_file = os.path.join(dest_dir, "config.ocio")

    if os.path.isfile(config_file):
        print("[ACES IO] ACES 1.2 config already present — OK")
        return

    url = (
        "https://github.com/colour-science/OpenColorIO-Configs/releases/download/"
        "v1.2/OpenColorIO-Config-ACES-1.2.zip"
    )
    print(f"[ACES IO] Downloading ACES 1.2 config from:\n  {url}")

    try:
        tmp_dir = tempfile.mkdtemp(prefix="aces_io_")
        zip_path = os.path.join(tmp_dir, "aces_1.2.zip")

        downloaded = 0
        last_printed_mb = 0
        PRINT_EVERY = 10 * 1024 * 1024  # 10 MB

        def _reporthook(block_num, block_size, total_size):
            nonlocal downloaded, last_printed_mb
            downloaded += block_size
            if downloaded - last_printed_mb >= PRINT_EVERY:
                mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024) if total_size > 0 else "?"
                print(f"[ACES IO]   {mb:.0f} MB / {total_mb} MB downloaded …")
                last_printed_mb = downloaded

        urllib.request.urlretrieve(url, zip_path, reporthook=_reporthook)
        print(f"[ACES IO] Download complete. Extracting …")

        extract_dir = os.path.join(tmp_dir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        # The zip contains a top-level folder named OpenColorIO-Config-ACES-1.2/
        src_dir = os.path.join(extract_dir, "OpenColorIO-Config-ACES-1.2")
        if not os.path.isdir(src_dir):
            # Fallback: find any directory inside extract_dir
            entries = [
                e for e in os.listdir(extract_dir)
                if os.path.isdir(os.path.join(extract_dir, e))
            ]
            if entries:
                src_dir = os.path.join(extract_dir, entries[0])
            else:
                raise RuntimeError(
                    f"[ACES IO] Could not locate config directory inside zip."
                )

        os.makedirs(dest_dir, exist_ok=True)
        shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
        print(f"[ACES IO] ACES 1.2 config installed to: {dest_dir}")

    except Exception as exc:
        raise RuntimeError(
            f"[ACES IO] Could not download ACES 1.2 config: {exc}\n"
            f"  URL: {url}\n"
            f"  Target: {dest_dir}\n"
            "  Check network connectivity or download the zip manually and extract it there."
        ) from exc
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    try_install_ocio()
    install_pip_deps()
    download_aces12()
