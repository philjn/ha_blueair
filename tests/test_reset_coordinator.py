"""Tests for ``BlueairUpdateCoordinatorDeviceAws._reset_consumable``.

This is where the failure-path logic lives — translating cloud failures,
auth errors, and bad inputs into ``HomeAssistantError`` so the HA UI
shows the user a notification instead of silently swallowing the press.

We bypass the DataUpdateCoordinator construction (which would require a
real HA instance) by allocating the coordinator via ``object.__new__``
and pinning just the attributes the method under test reads. This keeps
the failure-path coverage tight and independent of HA internals.
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError  # stub or real

from custom_components.ha_blueair.blueair_update_coordinator_device_aws import (
    BlueairUpdateCoordinatorDeviceAws,
)


def _run(coro):
    return asyncio.run(coro)


def _make_coordinator(device):
    """Allocate a coordinator instance without invoking the HA __init__."""
    coord = object.__new__(BlueairUpdateCoordinatorDeviceAws)
    coord.blueair_api_device = device
    coord.async_request_refresh = AsyncMock()
    return coord


def _device(**overrides):
    """A bare ``DeviceAws`` stand-in with the three reset methods mocked."""
    base = {
        "name": "My Purifier",
        "uuid": "dev-uuid",
        "reset_filter": AsyncMock(return_value=True),
        "reset_wick": AsyncMock(return_value=True),
        "reset_refresher": AsyncMock(return_value=True),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

def test_reset_filter_success_does_not_request_refresh():
    """On success we rely on the shadow update path; an immediate refresh
    would be a redundant /initial round-trip."""
    coord = _make_coordinator(_device())
    _run(coord.reset_filter())
    coord.blueair_api_device.reset_filter.assert_awaited_once_with()
    coord.async_request_refresh.assert_not_awaited()


def test_reset_wick_success_calls_underlying_device_method():
    coord = _make_coordinator(_device())
    _run(coord.reset_wick())
    coord.blueair_api_device.reset_wick.assert_awaited_once_with()
    coord.blueair_api_device.reset_filter.assert_not_awaited()


def test_reset_refresher_success_calls_underlying_device_method():
    coord = _make_coordinator(_device())
    _run(coord.reset_refresher())
    coord.blueair_api_device.reset_refresher.assert_awaited_once_with()


# ---------------------------------------------------------------------------
# Cloud-side rejection (e.g. device offline) — bool False return
# ---------------------------------------------------------------------------

def test_cloud_rejection_raises_homeassistant_error_and_refreshes():
    """If the cloud says no (typically: device offline), we want the
    user to see a notification AND force a refresh so a stale offline
    flag gets re-evaluated promptly."""
    coord = _make_coordinator(_device(reset_filter=AsyncMock(return_value=False)))
    with pytest.raises(HomeAssistantError, match="offline"):
        _run(coord.reset_filter())
    coord.async_request_refresh.assert_awaited_once()


def test_cloud_rejection_log_message_mentions_ctype(caplog):
    caplog.set_level(
        logging.WARNING,
        logger="custom_components.ha_blueair.blueair_update_coordinator_device_aws",
    )
    coord = _make_coordinator(_device(reset_filter=AsyncMock(return_value=False)))
    with pytest.raises(HomeAssistantError):
        _run(coord.reset_filter())
    assert any(
        "ctype=filter" in rec.message and "rejected" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Library-side ValueError (unknown ctype) — should NOT trigger a refresh
# ---------------------------------------------------------------------------

def test_value_error_raises_homeassistant_error_without_refresh():
    """ValueError means the lib itself rejected the input; refreshing
    won't help and would just thrash the API."""
    coord = _make_coordinator(
        _device(reset_filter=AsyncMock(side_effect=ValueError("invalid ctype 'x'")))
    )
    with pytest.raises(HomeAssistantError, match="Cannot reset"):
        _run(coord.reset_filter())
    coord.async_request_refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# Generic exception (auth, transport, anything unexpected) — refresh then raise
# ---------------------------------------------------------------------------

def test_unexpected_exception_triggers_refresh_then_raises():
    """Auth / transport failures should kick a refresh (so the coordinator
    can re-authenticate before the user's next interaction) and still
    surface the failure to the UI."""
    boom = ConnectionError("token expired")
    coord = _make_coordinator(_device(reset_filter=AsyncMock(side_effect=boom)))
    with pytest.raises(HomeAssistantError, match="Failed to reset filter"):
        _run(coord.reset_filter())
    coord.async_request_refresh.assert_awaited_once()


def test_unexpected_exception_chains_original_cause():
    """The user-facing HomeAssistantError must carry the underlying
    exception in __cause__ so the HA log shows the actual root cause."""
    original = ConnectionError("token expired")
    coord = _make_coordinator(_device(reset_filter=AsyncMock(side_effect=original)))
    with pytest.raises(HomeAssistantError) as exc_info:
        _run(coord.reset_filter())
    assert exc_info.value.__cause__ is original


def test_unexpected_exception_is_logged_with_traceback(caplog):
    """_LOGGER.exception captures the traceback for post-mortem debug."""
    caplog.set_level(
        logging.ERROR,
        logger="custom_components.ha_blueair.blueair_update_coordinator_device_aws",
    )
    boom = ConnectionError("token expired")
    coord = _make_coordinator(_device(reset_filter=AsyncMock(side_effect=boom)))
    with pytest.raises(HomeAssistantError):
        _run(coord.reset_filter())
    matching = [
        rec for rec in caplog.records if "Consumable reset failed" in rec.message
    ]
    assert matching
    # _LOGGER.exception adds traceback info to the record.
    assert any(rec.exc_info for rec in matching)


# ---------------------------------------------------------------------------
# device_name attribute resolution (defensive: works even if missing)
# ---------------------------------------------------------------------------

def test_reset_works_when_coordinator_lacks_device_name_attribute():
    """The helper falls back to a sensible default if device_name is
    unavailable for any reason."""
    coord = _make_coordinator(_device(reset_filter=AsyncMock(return_value=False)))
    # Don't set device_name as a property; rely on the helper's default.
    # (The real coordinator's device_name is a @property; using the
    # SimpleNamespace fallback covers the case where the property would
    # raise.)
    with pytest.raises(HomeAssistantError):
        _run(coord.reset_filter())
