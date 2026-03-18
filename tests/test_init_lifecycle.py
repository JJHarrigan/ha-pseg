"""Lifecycle tests for custom_components.psegli.__init__.py."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.psegli.const import DOMAIN
import custom_components.psegli as psegli_init


@pytest.mark.asyncio
async def test_unload_cleans_up_when_only_unloaded_entries_remain() -> None:
    """If no loaded entries remain, scheduled task/services must be cleaned up.

    Regression case: a second config entry may exist but be unloaded/disabled.
    Cleanup must key off loaded entries (present in hass.data[DOMAIN]), not all
    config entries returned by hass.config_entries.async_entries(DOMAIN).
    """
    runtime_data = SimpleNamespace(async_shutdown=AsyncMock())
    active_entry = SimpleNamespace(entry_id="entry_active", runtime_data=runtime_data)
    unloaded_entry = SimpleNamespace(entry_id="entry_unloaded", runtime_data=None)

    long_task = asyncio.create_task(asyncio.sleep(60))

    hass = SimpleNamespace(
        data={
            DOMAIN: {
                active_entry.entry_id: object(),
                "_scheduled_task_running": True,
                "_scheduled_task": long_task,
            }
        },
        config_entries=SimpleNamespace(
            async_entries=MagicMock(return_value=[active_entry, unloaded_entry])
        ),
        services=SimpleNamespace(async_remove=MagicMock()),
    )

    result = await psegli_init.async_unload_entry(hass, active_entry)

    assert result is True
    assert "_scheduled_task_running" not in hass.data[DOMAIN]
    assert "_scheduled_task" not in hass.data[DOMAIN]
    assert long_task.cancelled() or long_task.done()
    hass.services.async_remove.assert_any_call(DOMAIN, "update_statistics")
    hass.services.async_remove.assert_any_call(DOMAIN, "refresh_cookie")


@pytest.mark.asyncio
async def test_unload_keeps_scheduler_when_another_loaded_entry_exists() -> None:
    """Keep scheduler/services when another loaded entry still exists."""
    runtime_data = SimpleNamespace(async_shutdown=AsyncMock())
    active_entry = SimpleNamespace(entry_id="entry_active", runtime_data=runtime_data)
    other_loaded_entry = SimpleNamespace(entry_id="entry_loaded_2", runtime_data=None)

    long_task = asyncio.create_task(asyncio.sleep(60))

    hass = SimpleNamespace(
        data={
            DOMAIN: {
                active_entry.entry_id: object(),
                other_loaded_entry.entry_id: object(),
                "_scheduled_task_running": True,
                "_scheduled_task": long_task,
            }
        },
        config_entries=SimpleNamespace(
            async_entries=MagicMock(return_value=[active_entry, other_loaded_entry])
        ),
        services=SimpleNamespace(async_remove=MagicMock()),
    )

    result = await psegli_init.async_unload_entry(hass, active_entry)

    assert result is True
    assert hass.data[DOMAIN]["_scheduled_task_running"] is True
    assert hass.data[DOMAIN]["_scheduled_task"] is long_task
    assert not long_task.cancelled()
    hass.services.async_remove.assert_not_called()

    long_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await long_task


@pytest.mark.asyncio
async def test_unload_clears_addon_connectivity_state_for_clean_next_setup() -> None:
    """Last-entry unload should clear connectivity and circuit-breaker state."""
    runtime_data = SimpleNamespace(async_shutdown=AsyncMock())
    active_entry = SimpleNamespace(entry_id="entry_active", runtime_data=runtime_data)

    hass = SimpleNamespace(
        data={
            DOMAIN: {
                active_entry.entry_id: object(),
                "_scheduled_task_running": True,
                "_addon_transport_failure_count": 3,
                "_addon_circuit_open_until": object(),
                "_addon_circuit_open_for_url": "http://addon.example:8000",
                "_addon_last_failure_url": "http://addon.example:8000",
                "_last_addon_unreachable_notification_at": object(),
                "_last_working_addon_url": "http://working-addon:8000",
            }
        },
        config_entries=SimpleNamespace(
            async_entries=MagicMock(return_value=[active_entry])
        ),
        services=SimpleNamespace(async_remove=MagicMock()),
    )

    result = await psegli_init.async_unload_entry(hass, active_entry)

    assert result is True
    assert "_addon_transport_failure_count" not in hass.data[DOMAIN]
    assert "_addon_circuit_open_until" not in hass.data[DOMAIN]
    assert "_addon_circuit_open_for_url" not in hass.data[DOMAIN]
    assert "_addon_last_failure_url" not in hass.data[DOMAIN]
    assert "_last_addon_unreachable_notification_at" not in hass.data[DOMAIN]
    assert "_last_working_addon_url" not in hass.data[DOMAIN]
