# -*- mode: python ; coding: utf-8 -*-
# Build with: pyinstaller DSM_Optimizer.spec --clean --noconfirm
import os
import sys

datas = [
    ("server", "server"),          # includes server/static and the sample DSM
    ("dsm_optimizer", "dsm_optimizer"),
]

hidden = [
    "webview",
    "webview.platforms.winforms",   # Windows
    "webview.platforms.cocoa",      # macOS
    "webview.platforms.gtk",        # Linux
    "flask",
    "werkzeug",
    "jinja2",
    "sklearn",
    "sklearn.cluster",
    "sklearn.utils._cython_blas",
    "scipy",
    "scipy.sparse.csgraph._validation",
    "scipy.special.cython_special",
    "openpyxl",
    "matplotlib",
    "matplotlib.backends.backend_agg",
]

# Recent scipy/scikit-learn versions have optional "Array API" backend
# support that does a guarded `try: import torch / cupy / jax` for GPU
# interop. Nothing in this app touches that code path, but if any of these
# happen to be installed in the same environment you're building from
# (common if it's your general/global Python install rather than a clean
# venv), PyInstaller's static bytecode scanner still finds the guarded
# import and pulls the whole package in - torch alone can add 1-2GB and
# several minutes to the build for zero benefit here. Excluded explicitly
# rather than relying on them simply not being installed.
excludes = [
    "tkinter",
    "torch", "torchvision", "torchaudio",
    "tensorboard", "tensorflow",
    "pandas", "pyarrow",
    "IPython", "jupyter", "jupyter_client", "jupyter_core", "notebook",
    "pytest", "_pytest",
]

a = Analysis(
    ["desktop_launcher.py"],
    pathex=[os.getcwd()],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

# Splash screen (Windows/Linux only - PyInstaller has no macOS splash).
# Shows assets/splash.png immediately on launch, long before the heavy
# sklearn/scipy/matplotlib imports finish; desktop_launcher.py closes it
# via pyi_splash once the local server is up and the window opens.
splash = None
if sys.platform != "darwin":
    splash = Splash(
        "assets/splash.png",
        binaries=a.binaries,
        datas=a.datas,
        text_pos=None,
        always_on_top=True,
    )

exe = EXE(
    pyz,
    a.scripts,
    *( [splash] if splash else [] ),
    [],
    exclude_binaries=True,
    name="DSM_Optimizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",   # Windows taskbar/shortcut icon
)

coll = COLLECT(
    exe,
    *( [splash.binaries] if splash else [] ),
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DSM_Optimizer",
)

# macOS only: without this, the onedir executable above runs as a bare Unix
# binary and macOS shows "Python" in the menu bar / dock (it's inheriting the
# identity of the embedded Python runtime, not your app). BUNDLE() wraps the
# same build into a real .app with its own Info.plist, name, and icon.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="DSM Optimizer.app",
        icon="assets/icon.icns",
        bundle_identifier="com.chanchaldhiman.dsmoptimizer",
        info_plist={
            "CFBundleName": "DSM Optimizer",
            "CFBundleDisplayName": "DSM Optimizer",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
