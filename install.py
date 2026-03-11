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
    deps = ["numpy", "Pillow", "opencv-python"]
    if _pip(*deps) != 0:
        print(f"[ACES IO] Warning: could not install one or more of {deps}")


if __name__ == "__main__":
    try_install_ocio()
    install_pip_deps()
