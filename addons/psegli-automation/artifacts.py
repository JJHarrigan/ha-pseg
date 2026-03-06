#!/usr/bin/env python3
"""Persistent login-failure artifacts for add-on troubleshooting."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from datetime import UTC, datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_ARTIFACTS_DIR = "/data/login_failures"
DEFAULT_ARTIFACT_RETENTION = 10

_PASSWORD_OR_TOKEN_INPUT_RE = re.compile(
    r'(<input[^>]*(?:type=["\']password["\']|name=["\'](?:password|loginpassword|__requestverificationtoken)["\']|id=["\'](?:LoginPassword|__RequestVerificationToken)["\'])[^>]*\bvalue=["\'])([^"\']*)(["\'])',
    flags=re.IGNORECASE,
)
_EMAIL_INPUT_RE = re.compile(
    r'(<input[^>]*(?:name=["\'](?:email|loginemail)["\']|id=["\']LoginEmail["\'])[^>]*\bvalue=["\'])([^"\']*)(["\'])',
    flags=re.IGNORECASE,
)


def get_login_failure_artifacts_dir() -> str:
    """Return the artifact root; allow env override for local/dev tests."""
    return os.environ.get("PSEGLI_LOGIN_FAILURES_DIR", DEFAULT_ARTIFACTS_DIR)


def _sanitize_html(html: str) -> str:
    """Best-effort redaction for obvious credential/token form fields."""
    html = _PASSWORD_OR_TOKEN_INPUT_RE.sub(r"\1**REDACTED**\3", html)
    html = _EMAIL_INPUT_RE.sub(r"\1**REDACTED**\3", html)
    return html


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _artifact_dirs(root: str) -> list[str]:
    if not os.path.isdir(root):
        return []
    entries: list[str] = []
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            entries.append(path)
    # Timestamp-derived ids sort lexicographically in chronological order.
    entries.sort(key=lambda p: os.path.basename(p), reverse=True)
    return entries


def prune_login_failure_artifacts(keep: int = DEFAULT_ARTIFACT_RETENTION) -> None:
    """Prune older artifacts to keep only the newest N directories."""
    root = get_login_failure_artifacts_dir()
    keep = max(1, int(keep))

    try:
        dirs = _artifact_dirs(root)
        for path in dirs[keep:]:
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        _LOGGER.debug("Artifact prune failed for %s: %s", root, e)


def list_login_failure_artifacts(limit: int = DEFAULT_ARTIFACT_RETENTION) -> dict[str, Any]:
    """Return metadata-only listing of saved login-failure artifacts."""
    root = get_login_failure_artifacts_dir()
    limit = _normalize_limit(limit)
    items: list[dict[str, Any]] = []

    for artifact_dir in _artifact_dirs(root):
        artifact_id = os.path.basename(artifact_dir)
        metadata_path = os.path.join(artifact_dir, "metadata.json")
        metadata: dict[str, Any] = {}
        if os.path.isfile(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    metadata = loaded
            except (OSError, json.JSONDecodeError):
                metadata = {}

        item = {
            "id": metadata.get("id", artifact_id),
            "created_at": metadata.get("created_at"),
            "category": metadata.get("category"),
            "subreason": metadata.get("subreason"),
            "url": metadata.get("url"),
            "title": metadata.get("title"),
            "recaptcha_iframe": metadata.get("recaptcha_iframe"),
            "html_file": metadata.get("html_file", f"{artifact_id}/page.html"),
            "screenshot_file": metadata.get("screenshot_file", f"{artifact_id}/page.png"),
        }
        items.append(item)

    return {"count": len(items), "items": items[:limit]}


async def save_login_failure_artifact(
    *,
    page,
    category: str,
    subreason: str | None,
    url: str,
    title: str,
    recaptcha_iframe: bool,
) -> dict[str, Any] | None:
    """Persist HTML/screenshot + metadata for a failed login attempt."""
    root = get_login_failure_artifacts_dir()

    try:
        os.makedirs(root, exist_ok=True)
    except OSError as e:
        _LOGGER.warning("Could not create artifact directory %s: %s", root, e)
        return None

    artifact_id = str(int(time.time() * 1000))
    artifact_dir = os.path.join(root, artifact_id)
    html_path = os.path.join(artifact_dir, "page.html")
    screenshot_path = os.path.join(artifact_dir, "page.png")
    metadata_path = os.path.join(artifact_dir, "metadata.json")

    try:
        os.makedirs(artifact_dir, exist_ok=False)
        html = await page.content()
        sanitized_html = _sanitize_html(html)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(sanitized_html)

        await page.screenshot(path=screenshot_path, full_page=True)

        metadata = {
            "id": artifact_id,
            "created_at": _utc_now_iso(),
            "category": category,
            "subreason": subreason,
            "url": url,
            "title": title,
            "recaptcha_iframe": recaptcha_iframe,
            "html_file": f"{artifact_id}/page.html",
            "screenshot_file": f"{artifact_id}/page.png",
        }
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        return metadata
    except Exception as e:
        _LOGGER.warning("Failed to save login failure artifacts: %s", e)
        shutil.rmtree(artifact_dir, ignore_errors=True)
        return None

