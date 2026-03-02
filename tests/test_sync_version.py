"""Tests for scripts/sync_version.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_version.py"
SPEC = importlib.util.spec_from_file_location("sync_version", SCRIPT_PATH)
assert SPEC and SPEC.loader
sync_version = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync_version
SPEC.loader.exec_module(sync_version)


def _write(root: Path, rel_path: str, content: str) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_versioned_files(root: Path, version: str) -> None:
    _write(
        root,
        "repository.yaml",
        f'name: "repo"\nversion: "{version}"\n',
    )
    _write(
        root,
        "custom_components/psegli/manifest.json",
        '{\n  "domain": "psegli",\n  "version": "' + version + '",\n  "config_flow": true\n}\n',
    )
    _write(
        root,
        "addons/psegli-automation/config.yaml",
        f'name: "addon"\nversion: "{version}"\n',
    )
    _write(
        root,
        "addons/psegli-automation/build.yaml",
        f'name: "addon"\nversion: "{version}"\n',
    )
    _write(
        root,
        "addons/psegli-automation/run.py",
        'app = FastAPI(title="PSEG Long Island Automation", version="' + version + '")\n',
    )
    _write(
        root,
        "addons/psegli-automation/README.md",
        f"# Addon\n\n**Version**: {version}\n",
    )


def test_sync_version_updates_all_targets(tmp_path: Path) -> None:
    _seed_versioned_files(tmp_path, "1.0.0")

    changed = sync_version.sync_version(tmp_path, "9.9.9", check_only=False)

    assert set(changed) == {t.path for t in sync_version.TARGETS}
    assert 'version: "9.9.9"' in (tmp_path / "repository.yaml").read_text(encoding="utf-8")
    assert '"version": "9.9.9"' in (
        tmp_path / "custom_components/psegli/manifest.json"
    ).read_text(encoding="utf-8")
    assert 'version: "9.9.9"' in (
        tmp_path / "addons/psegli-automation/config.yaml"
    ).read_text(encoding="utf-8")
    assert 'version: "9.9.9"' in (
        tmp_path / "addons/psegli-automation/build.yaml"
    ).read_text(encoding="utf-8")
    assert 'version="9.9.9"' in (
        tmp_path / "addons/psegli-automation/run.py"
    ).read_text(encoding="utf-8")
    assert "**Version**: 9.9.9" in (
        tmp_path / "addons/psegli-automation/README.md"
    ).read_text(encoding="utf-8")


def test_sync_version_check_mode_does_not_modify_files(tmp_path: Path) -> None:
    _seed_versioned_files(tmp_path, "1.2.3")

    changed = sync_version.sync_version(tmp_path, "9.9.9", check_only=True)

    assert set(changed) == {t.path for t in sync_version.TARGETS}
    assert 'version: "1.2.3"' in (tmp_path / "repository.yaml").read_text(encoding="utf-8")


def test_validate_version_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        sync_version.validate_version("2.5")


def test_validate_version_accepts_hotfix_format() -> None:
    sync_version.validate_version("2.5.0.5")
