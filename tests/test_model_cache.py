import hashlib
import io
import json

import pytest

from scripts import fetch_model


@pytest.fixture
def model_manifest(tmp_path, monkeypatch):
    content = b"pinned model bytes"
    manifest = {
        "repository": "example/model",
        "revision": "a" * 40,
        "files": {
            "ema.pt": {
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        },
    }
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(fetch_model, "MANIFEST", manifest_file)
    return manifest, content


def test_download_builds_plain_pinned_snapshot(tmp_path, monkeypatch, model_manifest):
    manifest, content = model_manifest
    requested = []

    def download(request, timeout):
        requested.append(request.full_url)
        return io.BytesIO(content)

    monkeypatch.setattr(fetch_model.urllib.request, "urlopen", download)
    cache = tmp_path / "cache"
    fetch_model.prepare_cache(cache)
    snapshot = cache / "models--example--model" / "snapshots" / manifest["revision"] / "ema.pt"
    reference = cache / "models--example--model" / "refs" / "main"
    assert snapshot.read_bytes() == content
    assert not snapshot.is_symlink()
    assert reference.read_text(encoding="utf-8") == manifest["revision"]
    assert requested == [
        f"https://huggingface.co/example/model/resolve/{manifest['revision']}/ema.pt"
    ]

    def no_network(*args, **kwargs):
        raise AssertionError("Verified cache must not access the network")

    monkeypatch.setattr(fetch_model.urllib.request, "urlopen", no_network)
    fetch_model.prepare_cache(cache, verify_only=True)
    fetch_model.prepare_cache(cache)


def test_bad_download_never_sets_reference(tmp_path, monkeypatch, model_manifest):
    _manifest, content = model_manifest
    monkeypatch.setattr(
        fetch_model.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"x" * len(content))
    )
    cache = tmp_path / "cache"
    with pytest.raises(RuntimeError, match="Checksum verification failed"):
        fetch_model.prepare_cache(cache)
    assert not list(cache.rglob("*.part"))
    assert not (cache / "models--example--model" / "refs" / "main").exists()


def test_verify_only_rejects_missing_files_without_network(tmp_path, monkeypatch, model_manifest):
    def no_network(*args, **kwargs):
        raise AssertionError("verify-only must never access the network")

    monkeypatch.setattr(fetch_model.urllib.request, "urlopen", no_network)
    with pytest.raises(RuntimeError, match="Missing or invalid model file"):
        fetch_model.prepare_cache(tmp_path / "missing", verify_only=True)
