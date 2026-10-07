"""Download and verify the pinned EMA weights into a portable HF cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "resources" / "model-manifest.json"


def verify_file(path: Path, expected: dict) -> bool:
    if not path.is_file() or path.stat().st_size != expected["size"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == expected["sha256"]


def prepare_cache(cache: Path, verify_only: bool = False) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    repository = manifest["repository"]
    revision = manifest["revision"]
    model_cache = cache / ("models--" + repository.replace("/", "--"))
    snapshot = model_cache / "snapshots" / revision
    for filename, expected in manifest["files"].items():
        target = snapshot / filename
        if verify_file(target, expected):
            print(f"Verified {filename}", flush=True)
            continue
        if verify_only:
            raise RuntimeError(f"Missing or invalid model file: {target}")
        snapshot.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        request = urllib.request.Request(
            f"https://huggingface.co/{repository}/resolve/{revision}/{filename}",
            headers={"User-Agent": "MascotReader-build/0.1"},
        )
        print(f"Downloading {filename} ({expected['size'] / 1024 / 1024:.1f} MiB)", flush=True)
        try:
            with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            if not verify_file(partial, expected):
                raise RuntimeError(f"Checksum verification failed: {filename}")
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
    reference = model_cache / "refs" / "main"
    if verify_only:
        if not reference.is_file() or reference.read_text(encoding="utf-8").strip() != revision:
            raise RuntimeError(f"Missing or invalid offline model reference: {reference}")
    else:
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_text(revision, encoding="utf-8")
    print(f"Offline cache ready: {cache}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "resources" / "model-cache")
    parser.add_argument("--verify-only", action="store_true", help="Verify locally without any network request.")
    options = parser.parse_args()
    try:
        prepare_cache(options.cache_dir.resolve(), options.verify_only)
    except (OSError, RuntimeError, urllib.error.URLError) as error:
        print(f"Model preparation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
