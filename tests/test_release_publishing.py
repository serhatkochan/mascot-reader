import copy
import hashlib
import json
import subprocess

import pytest

from scripts.publish_release import PublicationError, publish_release

REPO = "serhatkochan/mascot-reader"
SETUP = "MascotReader-Setup.exe"
CHECKSUM = SETUP + ".sha256"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def project(tmp_path):
    (tmp_path / "dist" / "MascotReader").mkdir(parents=True)
    (tmp_path / "build" / "verification").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.2.0"\n', encoding="utf-8")
    application = tmp_path / "dist" / "MascotReader" / "MascotReader.exe"
    application.write_bytes(b"frozen application version 0.2.0")
    installer = tmp_path / "dist" / SETUP
    installer.write_bytes(b"verified installer payload")
    installer.with_suffix(".exe.sha256").write_bytes(
        f"{sha256(installer.read_bytes())}  {SETUP}\r\n".encode("ascii")
    )
    summary = {
        "version": "0.2.0", "installer": str(installer), "bytes": installer.stat().st_size,
        "sha256": sha256(installer.read_bytes()),
        "application_exe_sha256": sha256(application.read_bytes()),
        "app_id": "{stable-id}", "compiler": "C:/Inno/ISCC.exe", "manifest_files": 3,
    }
    (tmp_path / "build" / "verification" / "installer-summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    notes = tmp_path / "notes with spaces.md"
    notes.write_text("# 0.2.0\nKurulabilir Windows sürümü.\n", encoding="utf-8")
    return tmp_path, notes


def asset(identifier, name, data):
    return {"id": identifier, "name": name, "state": "uploaded", "size": len(data),
            "digest": "sha256:" + sha256(data)}


def current_release(root):
    return {
        "id": 200, "tag_name": "v0.2.0", "draft": False, "prerelease": False,
        "html_url": "https://github.com/serhatkochan/mascot-reader/releases/tag/v0.2.0",
        "assets": [asset(201, SETUP, (root / "dist" / SETUP).read_bytes()),
                   asset(202, CHECKSUM, (root / "dist" / CHECKSUM).read_bytes())],
    }


class FakeGh:
    def __init__(self, release, *, exists=False, old=None):
        self.release = copy.deepcopy(release)
        self.exists = exists
        self.old = copy.deepcopy(old or [])
        self.calls = []
        self.create_failure = None
        self.create_exception = None
        self.create_stored = True
        self.lookup_failure = None
        self.latest_id = release["id"]
        self.delete_failure = None
        self.list_failure = None
        self.asset_list_failure = None
        self.source_status = ""
        self.head = "a" * 40
        self.local_tag = self.head
        self.remote_tag = self.head
        self.remote_annotated = True
        self.remote_missing = False
        self.git_failure = None

    def __call__(self, command):
        self.calls.append(command)
        if command[:2] == ["git", "-C"]:
            if self.git_failure:
                return subprocess.CompletedProcess(command, 1, "", self.git_failure)
            if command[3] == "status":
                assert "--porcelain" in command and "--untracked-files=normal" in command
                value = self.source_status
            elif command[3] == "rev-parse":
                value = self.head if command[-1] == "HEAD" else self.local_tag
            elif command[3] == "ls-remote":
                assert f"https://github.com/{REPO}.git" in command
                value = ""
                if not self.remote_missing:
                    value = "b" * 40 + "\trefs/tags/v0.2.0\n"
                    if self.remote_annotated:
                        value += self.remote_tag + "\trefs/tags/v0.2.0^{}\n"
            else:
                raise AssertionError(f"Unexpected Git operation: {command}")
            return subprocess.CompletedProcess(command, 0, value, "")
        if command[:3] == ["gh", "release", "create"]:
            if self.create_stored:
                self.exists = True
            if self.create_exception:
                raise self.create_exception
            if self.create_failure:
                return subprocess.CompletedProcess(command, 1, "", self.create_failure)
            return subprocess.CompletedProcess(command, 0, self.release["html_url"], "")
        assert command[:2] == ["gh", "api"]
        endpoint = command[2]
        if command[-2:] == ["--method", "DELETE"]:
            identifier = int(endpoint.rsplit("/", 1)[-1])
            if identifier == self.delete_failure:
                return subprocess.CompletedProcess(command, 1, "", "gh: forbidden (HTTP 403)")
            for release in self.old:
                release["assets"] = [item for item in release["assets"] if item["id"] != identifier]
            return subprocess.CompletedProcess(command, 0, "", "")
        if endpoint.endswith("/releases/tags/v0.2.0"):
            if self.lookup_failure:
                return subprocess.CompletedProcess(command, 1, "", self.lookup_failure)
            if not self.exists:
                return subprocess.CompletedProcess(command, 1, "", "gh: Not Found (HTTP 404)")
            value = self.release
        elif endpoint.endswith("/releases/latest"):
            value = dict(self.release, id=self.latest_id)
        elif endpoint.endswith("/releases?per_page=100"):
            assert "--paginate" in command and "--slurp" in command
            if self.list_failure:
                return subprocess.CompletedProcess(command, 1, "", self.list_failure)
            value = [[self.release], self.old[:1], self.old[1:]]
        elif "/releases/" in endpoint and endpoint.endswith("/assets?per_page=100"):
            assert "--paginate" in command and "--slurp" in command
            identifier = int(endpoint.split("/releases/")[1].split("/")[0])
            if identifier == self.asset_list_failure:
                return subprocess.CompletedProcess(command, 1, "", "gh: API failure (HTTP 503)")
            items = next(release["assets"] for release in self.old if release["id"] == identifier)
            value = [items[:1], items[1:]]
        else:
            raise AssertionError(f"Unexpected gh operation: {command}")
        return subprocess.CompletedProcess(command, 0, json.dumps(value), "")

    @property
    def deleted_ids(self):
        return [int(call[2].rsplit("/", 1)[-1]) for call in self.calls
                if call[-2:] == ["--method", "DELETE"]]

    @property
    def github_calls(self):
        return [call for call in self.calls if call[0] == "gh"]


def old_release(identifier=100, *, draft=False):
    return {"id": identifier, "tag_name": "v0.1.0", "draft": draft,
            "assets": [asset(101, SETUP, b"old installer"),
                       asset(102, CHECKSUM, b"old checksum"),
                       asset(103, "MascotReader-windows-x64.zip", b"old portable"),
                       asset(104, "MascotReader-windows-x64.zip.sha256", b"old portable sum"),
                       asset(105, "user-guide.pdf", b"keep this document")]}


def test_verified_publication_removes_only_managed_assets_from_all_old_pages(project):
    root, notes = project
    first = old_release()
    second = old_release(300)
    second["assets"] = [asset(301, "MascotReader-windows-x64.zip", b"older portable")]
    gh = FakeGh(current_release(root), old=[first, second])

    result = publish_release(root, notes, runner=gh)

    assert result["tag"] == "v0.2.0" and result["release_id"] == 200
    assert result["deleted_asset_ids"] == [101, 102, 103, 104, 301]
    assert [entry["name"] for entry in gh.old[0]["assets"]] == ["user-guide.pdf"]
    assert gh.release["assets"] == current_release(root)["assets"]
    create = next(call for call in gh.calls if call[:3] == ["gh", "release", "create"])
    assert "--verify-tag" in create and "--latest" in create
    assert create[create.index("--notes-file") + 1] == str(notes)
    assert str(root / "dist" / SETUP) in create and str(root / "dist" / CHECKSUM) in create
    assert not any("--clobber" in call for call in gh.calls)
    assert all(call[3] in ("status", "rev-parse", "ls-remote")
               for call in gh.calls if call[0] == "git")


@pytest.mark.parametrize("damage", ["missing_summary", "version", "installer_hash", "bytes",
                                    "application_hash", "checksum_hash", "checksum_name", "notes"])
def test_invalid_local_inputs_do_not_contact_github(project, damage):
    root, notes = project
    report = root / "build" / "verification" / "installer-summary.json"
    summary = json.loads(report.read_text(encoding="utf-8"))
    if damage == "missing_summary":
        report.unlink()
    elif damage in ("version", "installer_hash", "bytes", "application_hash"):
        key = {"installer_hash": "sha256", "application_hash": "application_exe_sha256"}.get(
            damage, damage
        )
        summary[key] = 1 if damage == "bytes" else "stale"
        report.write_text(json.dumps(summary), encoding="utf-8")
    elif damage == "notes":
        notes.unlink()
    else:
        checksum = root / "dist" / CHECKSUM
        value = checksum.read_text(encoding="ascii")
        if damage == "checksum_hash":
            value = "0" * 64 + value[64:]
        else:
            value = value.replace(SETUP, "other.exe")
        checksum.write_text(value, encoding="ascii")
    gh = FakeGh(current_release(root))

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.calls == []


@pytest.mark.parametrize("damage", ["draft", "prerelease", "tag", "setup_digest", "sha_digest",
                                    "size", "state", "missing_asset", "unknown_asset", "duplicate"])
def test_remote_verification_failure_never_deletes_old_assets(project, damage):
    root, notes = project
    release = current_release(root)
    if damage in ("draft", "prerelease"):
        release[damage] = True
    elif damage == "tag":
        release["tag_name"] = "v0.1.0"
    elif damage == "setup_digest":
        release["assets"][0]["digest"] = "sha256:" + "0" * 64
    elif damage == "sha_digest":
        release["assets"][1]["digest"] = "sha256:" + "0" * 64
    elif damage == "size":
        release["assets"][0]["size"] += 1
    elif damage == "state":
        release["assets"][0]["state"] = "starter"
    elif damage == "missing_asset":
        release["assets"].pop()
    elif damage == "unknown_asset":
        release["assets"].append(asset(203, "unrequested.zip", b"unexpected"))
    else:
        release["assets"].append(copy.deepcopy(release["assets"][0]))
    gh = FakeGh(release, old=[old_release()])

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.deleted_ids == []
    assert len(gh.old[0]["assets"]) == 5


def test_existing_verified_current_release_is_not_changed_or_reuploaded(project):
    root, notes = project
    release = current_release(root)
    gh = FakeGh(release, exists=True, old=[old_release()])

    result = publish_release(root, notes, runner=gh)

    assert result["deleted_asset_ids"] == [101, 102, 103, 104]
    assert gh.release == release
    assert all(call[:3] != ["gh", "release", "create"] for call in gh.calls)
    assert all("/releases/assets/20" not in call[2] for call in gh.calls)


def test_existing_draft_is_not_published_or_changed(project):
    root, notes = project
    release = current_release(root)
    release["draft"] = True
    gh = FakeGh(release, exists=True, old=[old_release()])

    with pytest.raises(PublicationError, match="draft|published"):
        publish_release(root, notes, runner=gh)

    assert gh.release == release
    assert all(call[:3] != ["gh", "release", "create"] for call in gh.calls)
    assert gh.deleted_ids == []


def test_upload_command_error_recovers_only_when_exact_release_was_stored(project):
    root, notes = project
    gh = FakeGh(current_release(root), old=[old_release()])
    gh.create_failure = "connection lost after upload"

    result = publish_release(root, notes, runner=gh)

    assert result["release_id"] == 200
    assert gh.deleted_ids == [101, 102, 103, 104]


def test_failed_upload_without_verified_remote_outcome_keeps_all_old_assets(project):
    root, notes = project
    gh = FakeGh(current_release(root), old=[old_release()])
    gh.create_failure = "connection lost before upload"
    gh.create_stored = False

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.deleted_ids == []
    assert len(gh.old[0]["assets"]) == 5


def test_non_404_lookup_failure_never_attempts_to_create_or_delete(project):
    root, notes = project
    gh = FakeGh(current_release(root), old=[old_release()])
    gh.lookup_failure = "gh: unauthorized (HTTP 401)"

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert len(gh.github_calls) == 1 and gh.deleted_ids == []


def test_non_latest_current_release_does_not_clean_previous_releases(project):
    root, notes = project
    gh = FakeGh(current_release(root), exists=True, old=[old_release()])
    gh.latest_id = 999

    with pytest.raises(PublicationError, match="latest"):
        publish_release(root, notes, runner=gh)

    assert gh.deleted_ids == []


def test_draft_old_release_and_unknown_assets_remain_untouched(project):
    root, notes = project
    unpublished = old_release(300, draft=True)
    gh = FakeGh(current_release(root), old=[unpublished])

    result = publish_release(root, notes, runner=gh)

    assert result["deleted_asset_ids"] == []
    assert gh.old[0] == unpublished


def test_cleanup_listing_failure_leaves_verified_current_and_all_old_assets(project):
    root, notes = project
    gh = FakeGh(current_release(root), old=[old_release()])
    gh.list_failure = "gh: API temporarily unavailable (HTTP 503)"

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.release == current_release(root)
    assert gh.deleted_ids == []


def test_cleanup_delete_failure_stops_and_never_rolls_back_current_release(project):
    root, notes = project
    gh = FakeGh(current_release(root), old=[old_release()])
    gh.delete_failure = 102

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.deleted_ids == [101, 102]
    assert gh.release == current_release(root)
    assert [entry["id"] for entry in gh.old[0]["assets"]] == [102, 103, 104, 105]


def test_create_timeout_recovers_by_verifying_the_stored_release(project):
    root, notes = project
    gh = FakeGh(current_release(root), old=[old_release()])
    gh.create_exception = subprocess.TimeoutExpired("gh release create", 1800)

    result = publish_release(root, notes, runner=gh)

    assert result["release_id"] == 200
    assert gh.deleted_ids == [101, 102, 103, 104]


def test_existing_release_with_different_installer_is_never_overwritten(project):
    root, notes = project
    release = current_release(root)
    release["assets"][0]["digest"] = "sha256:" + "0" * 64
    gh = FakeGh(release, exists=True, old=[old_release()])

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.github_calls == [["gh", "api", f"repos/{REPO}/releases/tags/v0.2.0"]]
    assert gh.release == release
    assert gh.deleted_ids == []


def test_all_old_assets_are_inspected_before_any_destructive_cleanup(project):
    root, notes = project
    gh = FakeGh(current_release(root), old=[old_release(), old_release(300)])
    gh.asset_list_failure = 300

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.deleted_ids == []
    assert all(len(previous["assets"]) == 5 for previous in gh.old)


def test_invalid_old_asset_id_never_causes_partial_cleanup(project):
    root, notes = project
    previous = old_release()
    previous["assets"][3]["id"] = "104"
    gh = FakeGh(current_release(root), old=[previous])

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.deleted_ids == []


def test_current_asset_id_cannot_be_deleted_through_a_malformed_old_release(project):
    root, notes = project
    previous = old_release()
    previous["assets"][0]["id"] = 201
    gh = FakeGh(current_release(root), old=[previous])

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.deleted_ids == []


def test_script_requires_explicit_release_notes_before_contacting_github(monkeypatch):
    from scripts.publish_release import main

    monkeypatch.setattr("sys.argv", ["publish_release.py"])
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 2


@pytest.mark.parametrize("damage", ["tracked", "untracked", "local_tag", "remote_tag",
                                    "remote_lightweight", "remote_missing", "git_error"])
def test_source_and_tag_mismatch_prevents_publication_and_cleanup(project, damage):
    root, notes = project
    gh = FakeGh(current_release(root), old=[old_release()])
    if damage == "tracked":
        gh.source_status = " M src/mascot_reader/window.py\n"
    elif damage == "untracked":
        gh.source_status = "?? src/mascot_reader/new_source.py\n"
    elif damage == "local_tag":
        gh.local_tag = "c" * 40
    elif damage == "remote_tag":
        gh.remote_tag = "c" * 40
    elif damage == "remote_lightweight":
        gh.remote_annotated = False
    elif damage == "remote_missing":
        gh.remote_missing = True
    else:
        gh.git_failure = "fatal: could not read repository"

    with pytest.raises(PublicationError):
        publish_release(root, notes, runner=gh)

    assert gh.github_calls == []
    assert gh.deleted_ids == []
    assert len(gh.old[0]["assets"]) == 5
