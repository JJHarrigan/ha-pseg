"""Tests for Home Assistant diagnostics export."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.psegli.const import (
    CONF_COOKIE,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.psegli.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.asyncio
async def test_diagnostics_redacts_sensitive_config_entry_fields(
    mock_hass, mock_config_entry
):
    """Diagnostics payload redacts cookie and credential fields."""
    mock_hass.data[DOMAIN] = {}

    diagnostics = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)

    entry = diagnostics["config_entry"]
    assert entry["entry_id"] == mock_config_entry.entry_id
    assert entry["data"][CONF_COOKIE] == "**REDACTED**"
    assert entry["data"][CONF_PASSWORD] == "**REDACTED**"
    assert entry["data"][CONF_USERNAME] == "**REDACTED**"


@pytest.mark.asyncio
async def test_diagnostics_includes_current_signal_snapshot(mock_hass, mock_config_entry):
    """Diagnostics payload includes the same signal model as get_status."""
    now = datetime.now(tz=timezone.utc)
    mock_hass.data[DOMAIN] = {
        "_cookie_obtained_at": now - timedelta(seconds=90),
        "_last_auth_probe_result": "ok",
        "_last_refresh_result": "success",
        "_last_refresh_reason": "scheduled",
        "_consecutive_auth_failures": 2,
        "_last_successful_update_at": now,
    }

    diagnostics = await async_get_config_entry_diagnostics(mock_hass, mock_config_entry)

    signals = diagnostics["signals"]
    assert signals["last_auth_probe_result"] == "ok"
    assert signals["last_refresh_result"] == "success"
    assert signals["last_refresh_reason"] == "scheduled"
    assert signals["consecutive_auth_failures"] == 2
    assert signals["last_successful_update_at"] == now.isoformat()
    assert signals["cookie_age_seconds"] is not None
    assert signals["cookie_age_seconds"] >= 60
