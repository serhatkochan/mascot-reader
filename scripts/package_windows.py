"""Refresh release documents and create the portable ZIP with its SHA256."""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    distribution = ROOT / "dist" / "MascotReader"
    if not (distribution / "MascotReader.exe").is_file():
        raise RuntimeError("Build MascotReader.exe before creating the portable ZIP.")
    for filename in ("README.md", "requirements-lock.txt"):
        shutil.copy2(ROOT / filename, distribution / filename)
    documents = distribution / "docs"
    documents.mkdir(exist_ok=True)
    for source in (ROOT / "docs").glob("*.md"):
        shutil.copy2(source, documents / source.name)
    assets = ROOT / "docs" / "assets"
    if assets.is_dir():
        shutil.copytree(assets, documents / "assets", dirs_exist_ok=True)
    legacy_verification = distribution / "verification.md"
    if legacy_verification.is_file():
        legacy_verification.unlink()
    licenses = distribution / "_internal" / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "resources" / "licenses").iterdir():
        if source.is_file():
            shutil.copy2(source, licenses / source.name)

    archive = ROOT / "dist" / "MascotReader-windows-x64.zip"
    partial = archive.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
            for source in sorted(distribution.rglob("*")):
                if source.is_file():
                    output.write(source, source.relative_to(distribution.parent).as_posix())
        partial.replace(archive)
    finally:
        partial.unlink(missing_ok=True)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    checksum = digest.hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    summary = {"archive": str(archive), "bytes": archive.stat().st_size, "sha256": checksum}
    report = ROOT / "build" / "verification" / "package-summary.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
