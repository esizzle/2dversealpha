"""Locate bundled files (fonts, audio) whether the game runs from source or
from a PyInstaller build.

Every asset path in the project goes through resource_path() so the game
never depends on the current working directory: launching main.py from
another folder, double-clicking a shortcut, or running the frozen exe from
the itch app all resolve to the same files.

    from resources import resource_path
    pygame.mixer.Sound(resource_path("assets/audio/sfx/cell_split.ogg"))

When frozen, PyInstaller extracts/places bundled data next to the runtime
and points sys._MEIPASS at it (one-dir builds: the _internal folder).
From source, the base is simply the folder this file lives in.
"""

import os
import sys

APP_NAME = "2dverse"
APP_VERSION = "Alpha 0.0.1"

IS_FROZEN = bool(getattr(sys, "frozen", False))

if IS_FROZEN:
    _BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    # the folder the exe itself lives in (writable-ish; used for the log file)
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = _BASE_DIR


def resource_path(relative):
    """Absolute path to a bundled resource, given a path relative to the
    project root (forward slashes are fine on every platform)."""
    return os.path.join(_BASE_DIR, *relative.replace("\\", "/").split("/"))


def redirect_output_when_frozen(filename="2dverse.log"):
    """In a --windowed PyInstaller build sys.stdout / sys.stderr are None,
    so every print() (audio warnings, cell counts, profiler dumps) and any
    traceback silently vanishes. Send them to a log file beside the exe
    instead, so a player can attach it to a bug report. No-op from source
    or if the folder is not writable."""
    if not IS_FROZEN:
        return
    if sys.stdout is not None and sys.stderr is not None:
        return  # console build: leave output where it is
    try:
        log = open(os.path.join(APP_DIR, filename), "a", buffering=1, encoding="utf-8")
    except OSError:
        return
    sys.stdout = log
    sys.stderr = log
    print(f"==== {APP_NAME} {APP_VERSION} started ====")
