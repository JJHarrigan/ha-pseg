#!/usr/bin/env python3
"""Synchronize release version across required metadata files.

Single source of truth: VERSION file at repository root.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    """A file + regex replacement rule that receives {version}."""

    path: str
    pattern: str
    replacement: str


TARGETS: tuple[Target, ...] = (
    Target(
        "repository.yaml",
        r'^(version:\s*")([^"]+)(")$',
        r'\g<1>{version}\g<3>',
    ),
    Target(
        "custom_components/psegli/manifest.json",
        r'^(\s*"version":\s*")([^"]+)(",?)$',
        r'\g<1>{version}\g<3>',
    ),
    Target(
        "addons/psegli-automation/config.yaml",
        r'^(version:\s*")([^"]+)(")$',
        r'\g<1>{version}\g<3>',
    ),
    Target(
        "addons/psegli-automation/build.yaml",
        r'^(version:\s*")([^"]+)(")$',
        r'\g<1>{version}\g<3>',
    ),
    Target(
        "addons/psegli-automation/run.py",
        r'^(app = FastAPI\(title="PSEG Long Island Automation", version=")([^"]+)("\))$',
        r'\g<1>{version}\g<3>',
    ),
    Target(
        "addons/psegli-automation/README.md",
        r'^(\*\*Version\*\*:\s*)(.+)$',
        r'\g<1>{version}',
    ),
)

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")


def validate_version(version: str) -> None:
    """Validate semantic version format used by this repo."""
    if not VERSION_RE.fullmatch(version):
        raise ValueError(
            f"Invalid version '{version}'. Expected format: MAJOR.MINOR.PATCH[.HOTFIX]"
        )


def _replace_once(text: str, target: Target, version: str) -> str:
    """Apply one replacement rule exactly once."""
    replacement = target.replacement.format(version=version)
    updated, count = re.subn(
        target.pattern,
        replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError(
            f"Could not update version in {target.path} with pattern: {target.pattern}"
        )
    return updated


def sync_version(root: Path, version: str, check_only: bool = False) -> list[str]:
    """Sync all target files to version.

    Returns list of files that were (or would be) changed.
    """
    changed: list[str] = []

    for target in TARGETS:
        file_path = root / target.path
        original = file_path.read_text(encoding="utf-8")
        updated = _replace_once(original, target, version)

        if original != updated:
            changed.append(target.path)
            if not check_only:
                file_path.write_text(updated, encoding="utf-8")

    return changed


def repo_root_from_script() -> Path:
    """Resolve repository root based on script location."""
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync repo version metadata.")
    parser.add_argument(
        "--set",
        dest="set_version",
        help="Write this version to VERSION first, then sync files",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether files are in sync without modifying them",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=repo_root_from_script(),
        help="Repository root (defaults to script-derived root)",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    version_file = root / "VERSION"

    if args.set_version:
        validate_version(args.set_version)
        version_file.write_text(f"{args.set_version}\n", encoding="utf-8")
        version = args.set_version
    else:
        version = version_file.read_text(encoding="utf-8").strip()
        validate_version(version)

    changed = sync_version(root, version, check_only=args.check)

    if args.check:
        if changed:
            print("Version mismatch detected in:")
            for path in changed:
                print(f" - {path}")
            return 1
        print(f"All versioned files are in sync at {version}.")
        return 0

    if changed:
        print(f"Synced version {version} in {len(changed)} file(s):")
        for path in changed:
            print(f" - {path}")
    else:
        print(f"No changes needed; files already synced at {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
