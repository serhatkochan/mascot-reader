import os
import sys
from pathlib import Path


def resource_dir() -> Path:
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    return root / "resources"


def configure_runtime() -> None:
    cache = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MascotReader"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_CACHE"] = str(resource_dir() / "model-cache")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["XDG_CACHE_HOME"] = str(cache / "cache")

