"""Buttons for Blueair devices.

Each button maps to a single one-shot action that doesn't fit naturally
into the switch / select / number model. Today the only such action is
resetting a consumable's life counter (filter / wick / refresher) after
the user has physically replaced the part.

The reset itself is a cloud REST call (not a shadow write); the
coordinator method ``reset_filter`` / ``reset_wick`` / ``reset_refresher``
translates the underlying ``bool`` result into a ``HomeAssistantError``
on failure so the press surfaces in the HA UI instead of silently
no-op'ing.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import BlueairEntity, async_setup_entry_helper

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Blueair button entities from a config entry."""
    async_setup_entry_helper(
        hass, config_entry, async_add_entities,
        entity_classes=[
            BlueairResetFilterButtonEntity,
            BlueairResetWickButtonEntity,
            BlueairResetRefresherButtonEntity,
        ],
    )


class BlueairResetButtonEntity(BlueairEntity, ButtonEntity):
    """Common base for the consumable-reset buttons.

    Subclasses set ``entity_description`` with three conventions baked in:

    - ``key`` is the **coordinator life property** (``filter_life``,
      ``wick_life``, ``water_refresher_life``). ``is_implemented`` reads
      it to decide whether to expose the button on this device.
    - The matching coordinator reset method is derived from the class
      attribute :attr:`_reset_method_name` so subclasses just declare
      the name once.
    - We tag every reset button as ``EntityCategory.CONFIG`` so they
      live in the "Configuration" section of the device card, not on the
      main controls strip.
    """

    #: Name of the coordinator method to call on press, e.g. ``reset_filter``.
    _reset_method_name: str

    @classmethod
    def is_implemented(kls, coordinator) -> bool:
        """Expose the button only when the device supports the consumable.

        Three gates:
        * The life property must not be ``NotImplemented`` — only devices
          that actually report this consumable on their shadow.
        * The coordinator must have the matching reset method — only the
          AWS coordinator does; the legacy coordinator has no reset path.
        * The underlying device must support the cloud-driven reset
          path. Older device families (B4, BluePremium, Classic) require
          a physical hold-the-fan-button reset on the device itself —
          the cloud REST endpoint returns ``status: 0`` but the device
          firmware ignores it. Exposing a button that silently no-ops
          would be confusing UX, so we skip those models entirely. See
          ``blueair_api.DeviceAws.supports_filter_reset_online`` for the
          hardware-prefix mapping and the empirical evidence it's based
          on. ``hasattr`` guards against older blueair_api releases that
          predate the property — falls back to "supported" so we never
          regress devices that worked before this gate was added.
        """
        key = kls.entity_description.key
        life_value = getattr(coordinator, key, NotImplemented)
        if life_value is NotImplemented:
            return False
        if not hasattr(coordinator, kls._reset_method_name):
            return False
        api_device = getattr(coordinator, "blueair_api_device", None)
        if api_device is not None and hasattr(
            api_device, "supports_filter_reset_online"
        ):
            if not api_device.supports_filter_reset_online:
                return False
        return True

    def __init__(self, coordinator):
        super().__init__(self.entity_description.name, coordinator)

    async def async_press(self) -> None:
        """Trigger the cloud-side consumable reset.

        Any failure (auth, transport, cloud rejection / device offline,
        invalid ctype) is converted by the coordinator into a
        ``HomeAssistantError``, which HA surfaces as a user-visible
        notification — the right UX for a manual, one-shot action.
        """
        reset_fn = getattr(self.coordinator, self._reset_method_name)
        _LOGGER.debug(
            "%s pressed; invoking %s on coordinator %s",
            self.entity_description.key,
            self._reset_method_name,
            self.coordinator.id,
        )
        await reset_fn()


class BlueairResetFilterButtonEntity(BlueairResetButtonEntity):
    """Reset the particulate filter life counter."""
    _reset_method_name = "reset_filter"
    entity_description = ButtonEntityDescription(
        key="filter_life",
        name="Reset Filter Life",
        icon="mdi:air-filter",
        entity_category=EntityCategory.CONFIG,
    )
    _attr_translation_key = "reset_filter"


class BlueairResetWickButtonEntity(BlueairResetButtonEntity):
    """Reset the humidifier wick life counter."""
    _reset_method_name = "reset_wick"
    entity_description = ButtonEntityDescription(
        key="wick_life",
        name="Reset Wick Life",
        icon="mdi:air-filter",
        entity_category=EntityCategory.CONFIG,
    )
    _attr_translation_key = "reset_wick"


class BlueairResetRefresherButtonEntity(BlueairResetButtonEntity):
    """Reset the water refresher life counter."""
    _reset_method_name = "reset_refresher"
    entity_description = ButtonEntityDescription(
        key="water_refresher_life",
        name="Reset Refresher Life",
        icon="mdi:air-filter",
        entity_category=EntityCategory.CONFIG,
    )
    _attr_translation_key = "reset_refresher"
