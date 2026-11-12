"""Buttons: shut down, restart, standby, hibernate, lock."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import PoweroffConfigEntry, async_send
from .entity import PoweroffEntity

PARALLEL_UPDATES = 1

BUTTONS: tuple[str, ...] = ("shutdown", "reboot", "standby", "hibernate", "lock")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoweroffConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one button per action."""
    async_add_entities(PoweroffButton(entry, command) for command in BUTTONS)


class PoweroffButton(PoweroffEntity, ButtonEntity):
    """Send one action to Poweroff."""

    def __init__(self, entry: PoweroffConfigEntry, command: str) -> None:
        """Initialize."""
        super().__init__(entry, command)
        self._command = command

    @property
    def available(self) -> bool:
        """Pressable even if the last check failed (it retries on its own)."""
        return True

    async def async_press(self) -> None:
        """Send the action, using the warning/force settings of the entry."""
        await async_send(self.hass, self._entry, self._command)
        await self.coordinator.async_request_refresh()
