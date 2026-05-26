"""Tests for the consumable-reset button entities.

We don't run the full BlueairEntity.__init__ (it would require the HA
DataUpdateCoordinator wiring); we construct the entity via
``object.__new__`` and exercise just the methods under test.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.ha_blueair.button import (
    BlueairResetButtonEntity,
    BlueairResetFilterButtonEntity,
    BlueairResetRefresherButtonEntity,
    BlueairResetWickButtonEntity,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# is_implemented gating
# ---------------------------------------------------------------------------

def _coord(**attrs):
    """Build a fake coordinator with arbitrary attributes."""
    return SimpleNamespace(**attrs)


def test_filter_button_implemented_when_life_and_method_present():
    coord = _coord(filter_life=85, reset_filter=AsyncMock())
    assert BlueairResetFilterButtonEntity.is_implemented(coord) is True


def test_filter_button_not_implemented_when_life_is_notimplemented():
    coord = _coord(filter_life=NotImplemented, reset_filter=AsyncMock())
    assert BlueairResetFilterButtonEntity.is_implemented(coord) is False


def test_filter_button_not_implemented_when_coordinator_lacks_reset_method():
    # Legacy (non-AWS) coordinators have filter_life but no reset_filter.
    coord = _coord(filter_life=85)
    assert BlueairResetFilterButtonEntity.is_implemented(coord) is False


def test_wick_button_uses_wick_life_key():
    coord_ok = _coord(wick_life=50, reset_wick=AsyncMock())
    coord_no_life = _coord(wick_life=NotImplemented, reset_wick=AsyncMock())
    coord_no_method = _coord(wick_life=50)
    assert BlueairResetWickButtonEntity.is_implemented(coord_ok) is True
    assert BlueairResetWickButtonEntity.is_implemented(coord_no_life) is False
    assert BlueairResetWickButtonEntity.is_implemented(coord_no_method) is False


def test_refresher_button_uses_water_refresher_life_key():
    coord_ok = _coord(water_refresher_life=50, reset_refresher=AsyncMock())
    coord_no_life = _coord(
        water_refresher_life=NotImplemented, reset_refresher=AsyncMock(),
    )
    coord_no_method = _coord(water_refresher_life=50)
    assert BlueairResetRefresherButtonEntity.is_implemented(coord_ok) is True
    assert BlueairResetRefresherButtonEntity.is_implemented(coord_no_life) is False
    assert BlueairResetRefresherButtonEntity.is_implemented(coord_no_method) is False


def test_buttons_are_independent_across_consumables():
    """A device with only a filter should not get wick / refresher buttons."""
    coord = _coord(
        filter_life=85, reset_filter=AsyncMock(),
        wick_life=NotImplemented,
        water_refresher_life=NotImplemented,
    )
    assert BlueairResetFilterButtonEntity.is_implemented(coord) is True
    assert BlueairResetWickButtonEntity.is_implemented(coord) is False
    assert BlueairResetRefresherButtonEntity.is_implemented(coord) is False


# ---------------------------------------------------------------------------
# supports_filter_reset_online hardware gate
# ---------------------------------------------------------------------------

def test_filter_button_hidden_when_device_requires_manual_reset():
    """Older device families (B4 / BluePremium / Classic) require a
    physical hold-the-fan-button reset on the device itself. The cloud
    REST endpoint returns success but the firmware ignores it, so
    exposing a button that silently no-ops would be confusing UX.

    The gate reads ``coordinator.blueair_api_device
    .supports_filter_reset_online``; when that is False the button must
    not be implemented even if life and the reset method are present.
    """
    api_device = SimpleNamespace(supports_filter_reset_online=False)
    coord = _coord(
        filter_life=85,
        reset_filter=AsyncMock(),
        blueair_api_device=api_device,
    )
    assert BlueairResetFilterButtonEntity.is_implemented(coord) is False


def test_filter_button_shown_when_device_supports_online_reset():
    api_device = SimpleNamespace(supports_filter_reset_online=True)
    coord = _coord(
        filter_life=85,
        reset_filter=AsyncMock(),
        blueair_api_device=api_device,
    )
    assert BlueairResetFilterButtonEntity.is_implemented(coord) is True


def test_filter_button_falls_back_to_supported_on_older_blueair_api():
    """``supports_filter_reset_online`` was added in a later blueair_api
    release; the gate must not regress devices that worked before this
    property existed. When the property is absent on the API device,
    treat the device as supported."""
    api_device_without_attr = SimpleNamespace()  # no supports_filter_reset_online
    coord = _coord(
        filter_life=85,
        reset_filter=AsyncMock(),
        blueair_api_device=api_device_without_attr,
    )
    assert BlueairResetFilterButtonEntity.is_implemented(coord) is True


def test_filter_button_falls_back_to_supported_when_blueair_api_device_missing():
    """Defensive: if blueair_api_device is None for any reason, don't
    block button exposure on that basis."""
    coord = _coord(
        filter_life=85,
        reset_filter=AsyncMock(),
        blueair_api_device=None,
    )
    assert BlueairResetFilterButtonEntity.is_implemented(coord) is True


def test_wick_button_respects_supports_filter_reset_online_gate():
    api_device = SimpleNamespace(supports_filter_reset_online=False)
    coord = _coord(
        wick_life=85,
        reset_wick=AsyncMock(),
        blueair_api_device=api_device,
    )
    assert BlueairResetWickButtonEntity.is_implemented(coord) is False


def test_refresher_button_respects_supports_filter_reset_online_gate():
    api_device = SimpleNamespace(supports_filter_reset_online=False)
    coord = _coord(
        water_refresher_life=85,
        reset_refresher=AsyncMock(),
        blueair_api_device=api_device,
    )
    assert BlueairResetRefresherButtonEntity.is_implemented(coord) is False


# ---------------------------------------------------------------------------
# async_press behavior
# ---------------------------------------------------------------------------

def _make_entity(kls, coordinator):
    """Construct an entity instance bypassing BlueairEntity.__init__."""
    entity = object.__new__(kls)
    entity.coordinator = coordinator
    return entity


def test_async_press_calls_matching_coordinator_method():
    coord = _coord(
        id="dev-uuid",
        reset_filter=AsyncMock(),
        reset_wick=AsyncMock(),
        reset_refresher=AsyncMock(),
    )
    entity = _make_entity(BlueairResetFilterButtonEntity, coord)
    _run(entity.async_press())
    coord.reset_filter.assert_awaited_once_with()
    coord.reset_wick.assert_not_awaited()
    coord.reset_refresher.assert_not_awaited()


def test_async_press_propagates_exceptions_from_coordinator():
    """If the coordinator raises (HomeAssistantError or anything else),
    we must let it propagate so HA's frontend can show the user."""

    async def boom():
        raise RuntimeError("offline")

    coord = _coord(id="dev-uuid", reset_filter=boom)
    entity = _make_entity(BlueairResetFilterButtonEntity, coord)
    with pytest.raises(RuntimeError, match="offline"):
        _run(entity.async_press())


@pytest.mark.parametrize(
    "kls,method,life_attr",
    [
        (BlueairResetFilterButtonEntity, "reset_filter", "filter_life"),
        (BlueairResetWickButtonEntity, "reset_wick", "wick_life"),
        (
            BlueairResetRefresherButtonEntity,
            "reset_refresher",
            "water_refresher_life",
        ),
    ],
)
def test_each_button_wired_to_the_right_method_and_key(kls, method, life_attr):
    """Cross-check the entity_description.key vs _reset_method_name."""
    assert kls.entity_description.key == life_attr
    assert kls._reset_method_name == method
    # Common entity-category baked in across all three.
    from homeassistant.const import EntityCategory  # uses stub or real
    assert kls.entity_description.entity_category == EntityCategory.CONFIG


def test_base_class_does_not_define_entity_description():
    """The base class should be abstract-ish — no entity_description."""
    assert not hasattr(BlueairResetButtonEntity, "entity_description")
