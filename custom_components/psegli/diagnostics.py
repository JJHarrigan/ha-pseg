"""Diagnostics support for PSEG Long Island integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import _build_status_snapshot
from .auto_login import get_addon_failure_artifacts
from .const import CONF_COOKIE, CONF_PASSWORD, CONF_USERNAME, DOMAIN

_TO_REDACT = {CONF_COOKIE, CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics payload for the selected config entry."""
    domain_data = hass.data.get(DOMAIN, {})
    entry_payload: dict[str, Any] = {
        "entry_id": config_entry.entry_id,
        "data": dict(config_entry.data),
        "options": dict(config_entry.options),
    }
    return {
        "config_entry": async_redact_data(entry_payload, _TO_REDACT),
        "signals": await _build_status_snapshot(
            hass,
            config_entry,
            domain_data,
            artifact_fetcher=get_addon_failure_artifacts,
        ),
    }
