"""Is Poweroff answering on the machine?"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PoweroffConfigEntry
from .entity import PoweroffEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoweroffConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the reachability sensor."""
    async_add_entities([PoweroffReachable(entry)])


class PoweroffReachable(PoweroffEntity, BinarySensorEntity):
    """On while Poweroff answers on its port (i.e. the machine is up)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: PoweroffConfigEntry) -> None:
        """Initialize."""
        super().__init__(entry, "reachable")

    @property
    def available(self) -> bool:
        """Always available: "off" is the answer when the machine is down."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether Poweroff answered on the last check."""
        return bool(self.coordinator.data)
