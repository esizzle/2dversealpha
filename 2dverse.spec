# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe for 2dverse.

Build (from the project folder, inside the build venv):
    pyinstaller 2dverse.spec --noconfirm --clean
or just run build.ps1, which also creates the venv and the itch.io zip.

Output: dist/2dverse/2dverse.exe + dist/2dverse/_internal/ (assets land at
_internal/assets, which is where resources.resource_path() looks when frozen).

One-dir rather than one-file on purpose: instant start-up (no unpacking to
%TEMP% on every launch), far fewer antivirus / SmartScreen false positives,
and itch.io's butler can patch it incrementally.
"""

from PyInstaller.utils.hooks import collect_all

# pygame and pymunk both ship their own PyInstaller hooks, so their DLLs and
# cffi backend are normally found automatically. collect_all(pymunk) is a
# belt-and-braces guard for the cffi extension (_chipmunk) -- cheap, ~2 MB.
pymunk_datas, pymunk_binaries, pymunk_hidden = collect_all("pymunk")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=pymunk_binaries,
    datas=[("assets", "assets")] + pymunk_datas,
    hiddenimports=pymunk_hidden,
    hookspath=[],
    runtime_hooks=[],
    # Nothing in the game uses these; excluding them keeps a build made from
    # a "fat" Python (e.g. Anaconda base) from dragging in hundreds of MB.
    excludes=[
        "numpy", "scipy", "matplotlib", "pandas", "PIL",
        "tkinter", "_tkinter", "IPython", "jupyter", "notebook",
        "pytest", "setuptools", "pkg_resources",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="2dverse",
    debug=False,
    strip=False,
    upx=False,           # UPX-packed exes are a common AV false-positive trigger
    # windowed: no console. prints/tracebacks go to 2dverse.log next to the
    # exe (see resources.redirect_output_when_frozen). Flip to True for a
    # build where you want to watch the output live.
    console=False,
    icon=None,           # set to "assets/icon.ico" once an icon exists
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="2dverse",
)
