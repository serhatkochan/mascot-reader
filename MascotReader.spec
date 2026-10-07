# ruff: noqa: F821

import importlib.metadata
import json
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
resources = root / "resources"
manifest = json.loads((resources / "model-manifest.json").read_text(encoding="utf-8"))
cache_name = "models--" + manifest["repository"].replace("/", "--")
cache = resources / "model-cache" / cache_name
snapshot = cache / "snapshots" / manifest["revision"]

datas = [
    (str(resources / "mascot.png"), "resources"),
    (str(resources / "mascot.json"), "resources"),
    (str(resources / "mascots"), "resources/mascots"),
    (str(resources / "model-manifest.json"), "resources"),
    (str(resources / "licenses"), "licenses"),
    (str(cache / "refs" / "main"), f"resources/model-cache/{cache_name}/refs"),
]
datas.extend(
    (str(snapshot / filename), f"resources/model-cache/{cache_name}/snapshots/{manifest['revision']}")
    for filename in manifest["files"]
)
for package in ("ema_lightning", "normalizer_tr"):
    datas.extend(collect_data_files(package))
datas.extend(copy_metadata("ema-lightning"))
datas.extend(copy_metadata("huggingface-hub"))

license_inventory = []
for distribution in importlib.metadata.distributions():
    package_name = distribution.metadata.get("Name", "unknown")
    safe_name = package_name.replace("/", "_").replace("\\", "_")
    found = []
    for entry in distribution.files or ():
        if any(part.lower().startswith(("license", "copying", "notice", "copyright")) for part in entry.parts):
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                destination = f"licenses/dependencies/{safe_name}/{entry.parent.as_posix()}"
                datas.append((str(source), destination))
                found.append(entry.as_posix())
    license_inventory.append({
        "name": package_name,
        "version": distribution.version,
        "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License"),
        "license_files": found,
    })
build_metadata = root / "build" / "licenses"
build_metadata.mkdir(parents=True, exist_ok=True)
inventory_path = build_metadata / "dependency-inventory.json"
inventory_path.write_text(json.dumps(sorted(license_inventory, key=lambda item: item["name"].lower()), ensure_ascii=False, indent=2), encoding="utf-8")
datas.append((str(inventory_path), "licenses"))
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    datas.append((str(python_license), "licenses/python"))

analysis = Analysis(
    [str(root / "scripts" / "launch_app.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("ema_lightning") + collect_submodules("normalizer_tr"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)
analysis.binaries = [
    item for item in analysis.binaries
    if not Path(item[0]).name.lower().startswith(("icu", "api-ms-win-", "ext-ms-win-"))
]
native_roots = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(), Path(os.environ["SystemRoot"]).resolve()]
for destination, source, _kind in analysis.binaries:
    if not any(Path(source).resolve().is_relative_to(allowed) for allowed in native_roots):
        raise RuntimeError(f"Unexpected external native dependency: {source} ({destination})")
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MascotReader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(resources / "mascot.ico") if (resources / "mascot.ico").is_file() else None,
)
collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="MascotReader",
)
