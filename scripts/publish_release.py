"""Publish the verified installer, then remove older managed release downloads."""

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "serhatkochan/mascot-reader"
SETUP_NAME = "MascotReader-Setup.exe"
MANAGED_ASSET_NAMES = {
    SETUP_NAME, SETUP_NAME + ".sha256",
    "MascotReader-windows-x64.zip", "MascotReader-windows-x64.zip.sha256",
}


class PublicationError(RuntimeError):
    pass


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local_artifacts(root: Path, notes_file: Path) -> tuple[str, list[dict]]:
    try:
        with (root / "pyproject.toml").open("rb") as stream:
            version = tomllib.load(stream)["project"]["version"]
        if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise PublicationError("The source version must be a stable major.minor.patch version.")
        summary = json.loads(
            (root / "build" / "verification" / "installer-summary.json").read_text(encoding="utf-8")
        )
        installer = root / "dist" / SETUP_NAME
        application = root / "dist" / "MascotReader" / "MascotReader.exe"
        checksum = installer.with_suffix(".exe.sha256")
        if not notes_file.is_file() or not notes_file.read_text(encoding="utf-8").strip():
            raise PublicationError("A nonempty --notes-file is required.")
        installer_hash = _file_hash(installer)
        if (summary["version"] != version
                or Path(summary["installer"]).resolve() != installer.resolve()
                or summary["bytes"] != installer.stat().st_size
                or summary["bytes"] <= 0
                or summary["sha256"] != installer_hash
                or summary["application_exe_sha256"] != _file_hash(application)):
            raise PublicationError("Installer build summary is stale; rebuild before publishing.")
        if checksum.read_text(encoding="ascii").strip() != f"{installer_hash}  {SETUP_NAME}":
            raise PublicationError("Installer SHA256 sidecar does not match the installer filename/hash.")
        artifacts = [{"name": path.name, "path": path, "sha256": _file_hash(path),
                      "bytes": path.stat().st_size} for path in (installer, checksum)]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise PublicationError(f"Cannot validate local release artifacts: {error}") from error
    return version, artifacts


def _run_command(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                          check=False, timeout=1800)


def _invoke(runner, arguments: list[str], *, program: str = "gh") -> subprocess.CompletedProcess:
    try:
        return runner([program, *arguments])
    except (OSError, subprocess.SubprocessError) as error:
        raise PublicationError(f"{program} could not complete the operation: {error}") from error


def _failure(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or "GitHub CLI failed").strip()


def _verify_source(runner, root: Path, tag: str, repo: str) -> str:
    def git(arguments: list[str]) -> str:
        result = _invoke(runner, ["-C", str(root), *arguments], program="git")
        if result.returncode:
            raise PublicationError(f"Source/tag verification failed: {_failure(result)}")
        return result.stdout.strip()

    if git(["status", "--porcelain", "--untracked-files=normal"]):
        raise PublicationError("Commit tracked and untracked source changes before publishing.")
    head = git(["rev-parse", "--verify", "HEAD"])
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", head):
        raise PublicationError("Git returned an invalid source commit SHA.")
    local_commit = git(["rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"])
    if local_commit != head:
        raise PublicationError("The local version tag does not point to the current source HEAD.")
    remote_ref = f"refs/tags/{tag}"
    remote = git(["ls-remote", "--exit-code", f"https://github.com/{repo}.git",
                  remote_ref, remote_ref + "^{}"])
    references = {}
    for line in remote.splitlines():
        fields = line.split()
        if (len(fields) != 2 or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", fields[0])
                or fields[1] in references):
            raise PublicationError("Git returned malformed remote tag references.")
        references[fields[1]] = fields[0]
    if remote_ref not in references or references.get(remote_ref + "^{}") != head:
        raise PublicationError("Push an annotated version tag pointing to the current source HEAD.")
    return head


def _json(result: subprocess.CompletedProcess):
    if result.returncode:
        raise PublicationError(_failure(result))
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise PublicationError("GitHub CLI returned invalid JSON.") from error


def _release_by_tag(runner, repo: str, tag: str):
    result = _invoke(runner, ["api", f"repos/{repo}/releases/tags/{tag}"])
    if result.returncode and "(HTTP 404)" in _failure(result):
        return None
    release = _json(result)
    if not isinstance(release, dict):
        raise PublicationError("GitHub release response is not an object.")
    return release


def _identifier(value) -> int:
    if type(value) is not int or value <= 0:
        raise PublicationError("GitHub returned an invalid release/asset ID.")
    return value


def _verify_release(release: dict, tag: str, artifacts: list[dict]) -> set[int]:
    if (release.get("tag_name") != tag or release.get("draft") is not False
            or release.get("prerelease") is not False):
        raise PublicationError("The current tag must be a published, stable release, never a draft.")
    _identifier(release.get("id"))
    assets = release.get("assets")
    if (not isinstance(assets, list) or len(assets) != len(artifacts)
            or not all(isinstance(item, dict) for item in assets)
            or {item.get("name") for item in assets} != {item["name"] for item in artifacts}):
        raise PublicationError("The current release must contain exactly the installer and SHA256.")
    identifiers = set()
    for artifact in artifacts:
        remote = next(item for item in assets if item["name"] == artifact["name"])
        identifier = _identifier(remote.get("id"))
        if (identifier in identifiers or remote.get("state") != "uploaded"
                or remote.get("size") != artifact["bytes"]
                or remote.get("digest") != "sha256:" + artifact["sha256"]):
            raise PublicationError(f"Remote size/state/SHA256 verification failed: {artifact['name']}")
        identifiers.add(identifier)
    return identifiers


def _paginated(runner, endpoint: str) -> list[dict]:
    pages = _json(_invoke(runner, ["api", endpoint, "--paginate", "--slurp"]))
    if (not isinstance(pages, list) or not all(isinstance(page, list) for page in pages)
            or not all(isinstance(item, dict) for page in pages for item in page)):
        raise PublicationError("GitHub returned malformed paginated release data.")
    return [item for page in pages for item in page]


def publish_release(root: Path, notes_file: Path, *, repo: str = DEFAULT_REPO, runner=None) -> dict:
    root = Path(root).resolve()
    notes_file = Path(notes_file).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise PublicationError("--repo must be an owner/repository name.")
    version, artifacts = _local_artifacts(root, notes_file)
    runner = runner or _run_command
    tag = "v" + version
    source_commit = _verify_source(runner, root, tag, repo)
    release = _release_by_tag(runner, repo, tag)
    if release is None:
        creation_failure = ""
        try:
            creation = _invoke(runner, [
                "release", "create", tag, *[str(item["path"]) for item in artifacts],
                "--repo", repo, "--verify-tag", "--latest", "--title", f"MascotReader {version}",
                "--notes-file", str(notes_file),
            ])
            if creation.returncode:
                creation_failure = _failure(creation)
        except PublicationError as error:
            creation_failure = str(error)
        # A lost response can follow a successful upload; inspect before deciding.
        release = _release_by_tag(runner, repo, tag)
        if release is None:
            raise PublicationError(creation_failure or "Release not visible after upload")
    current_assets = _verify_release(release, tag, artifacts)
    latest = _json(_invoke(runner, ["api", f"repos/{repo}/releases/latest"]))
    if (not isinstance(latest, dict) or latest.get("id") != release["id"]
            or latest.get("tag_name") != tag or latest.get("draft") is not False):
        raise PublicationError("The verified current release is not GitHub's latest release.")

    deletions = []
    visited = set()
    for previous in _paginated(runner, f"repos/{repo}/releases?per_page=100"):
        if previous.get("draft") is True:
            continue
        if previous.get("draft") is not False:
            raise PublicationError("GitHub returned a release without a published/draft state.")
        identifier = _identifier(previous.get("id"))
        if identifier == release["id"] or previous.get("tag_name") == tag or identifier in visited:
            continue
        visited.add(identifier)
        for item in _paginated(runner, f"repos/{repo}/releases/{identifier}/assets?per_page=100"):
            if item.get("name") in MANAGED_ASSET_NAMES:
                asset_id = _identifier(item.get("id"))
                if asset_id in current_assets:
                    raise PublicationError("Refusing to delete an asset belonging to the current release.")
                if asset_id not in deletions:
                    deletions.append(asset_id)

    deleted = []
    for asset_id in deletions:
        result = _invoke(runner, ["api", f"repos/{repo}/releases/assets/{asset_id}",
                                  "--method", "DELETE"])
        if result.returncode:
            raise PublicationError(
                f"Current release verified; old-asset cleanup stopped at {asset_id} "
                f"after deleting {deleted}: {_failure(result)}"
            )
        deleted.append(asset_id)
    return {"tag": tag, "release_id": release["id"], "url": release.get("html_url", ""),
            "source_commit": source_commit, "deleted_asset_ids": deleted}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes-file", type=Path, required=True)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    options = parser.parse_args()
    try:
        result = publish_release(ROOT, options.notes_file, repo=options.repo)
    except PublicationError as error:
        parser.exit(1, f"Release publication stopped: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
