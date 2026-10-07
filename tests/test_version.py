import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from mascot_reader import __version__


def test_version_report_does_not_initialize_gui_or_user_cache(tmp_path):
    report = tmp_path / 'reports' / 'version.json'
    profile = tmp_path / 'profile'
    environment = os.environ.copy()
    environment['LOCALAPPDATA'] = str(profile)
    result = subprocess.run(
        [sys.executable, '-m', 'mascot_reader', '--version-file', str(report)],
        env=environment, capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(report.read_text(encoding='utf-8')) == {
        'version': __version__, 'frozen': False,
    }
    assert not profile.exists()


def test_package_and_build_versions_match():
    configuration = Path(__file__).resolve().parents[1] / 'pyproject.toml'
    assert tomllib.loads(configuration.read_text(encoding='utf-8'))['project']['version'] == __version__
