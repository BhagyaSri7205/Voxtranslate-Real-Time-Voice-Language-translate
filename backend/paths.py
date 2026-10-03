import os
import sys
from pathlib import Path


def resource_path(*parts):
    """
    Path to a bundled, read-only resource (images, etc.) that works both
    when running normally and when frozen into a PyInstaller .exe.
    PyInstaller extracts bundled data to a temporary folder at
    sys._MEIPASS at runtime — this resolves against that when frozen,
    and against the project root otherwise.
    """
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent  # backend/ -> project root
    return base.joinpath(*parts)


def app_data_path(*parts):
    """
    Path to a file VoxTranslate needs to WRITE and keep across runs
    (the database, in particular). This must NOT live inside the
    PyInstaller temp extraction folder (sys._MEIPASS) — that folder is
    deleted after every run, which would silently wipe every user's
    account and translation history on each launch of the .exe.
    Instead, when frozen, this resolves next to the actual .exe file,
    which persists normally on disk like any other file next to it.
    """
    if os.environ.get("DATA_DIR"):  # hosting: persistent disk folder
        base = Path(os.environ["DATA_DIR"])
        base.mkdir(parents=True, exist_ok=True)
        return base.joinpath(*parts)
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent  # backend/ -> project root
    return base.joinpath(*parts)
