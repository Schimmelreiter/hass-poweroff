"""Common base for Poweroff entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PoweroffConfigEntry
from .const import DOMAIN


class PoweroffEntity(CoordinatorEntity):
    """Entity of one Poweroff machine."""

    _attr_has_entity_name = True

    def __init__(self, entry: PoweroffConfigEntry, key: str) -> None:
        """Bind to the entry's device."""
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Jorgen Bosman",
            model="Poweroff",
            configuration_url=None,
        )
