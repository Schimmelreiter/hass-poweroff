"""Shut down, restart or lock Windows machines running Poweroff (remote control)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import (
    PoweroffAuthError,
    PoweroffClient,
    PoweroffCommandError,
    PoweroffConnectionError,
)
from .const import (
    ATTR_COMMAND,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_FORCE,
    ATTR_MESSAGE,
    ATTR_SIMULATE,
    ATTR_WARNING_SECONDS,
    COMMANDS,
    CONF_FORCE,
    CONF_WARNING_MESSAGE,
    CONF_WARNING_SECONDS,
    DOMAIN,
    SCAN_INTERVAL,
    SERVICE_SEND_COMMAND,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_COMMAND): vol.In(COMMANDS),
        vol.Optional(ATTR_WARNING_SECONDS): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
        vol.Optional(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_FORCE): cv.boolean,
        vol.Optional(ATTR_SIMULATE, default=False): cv.boolean,
    }
)


@dataclass
class PoweroffData:
    """Runtime data of one config entry."""

    client: PoweroffClient
    coordinator: DataUpdateCoordinator[bool]


type PoweroffConfigEntry = ConfigEntry[PoweroffData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the send_command action."""

    async def _send_command(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY_ID])
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_found"
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"name": entry.title},
            )
        await async_send(
            hass,
            entry,
            call.data[ATTR_COMMAND],
            warning_seconds=call.data.get(ATTR_WARNING_SECONDS),
            message=call.data.get(ATTR_MESSAGE),
            force=call.data.get(ATTR_FORCE),
            simulate=call.data[ATTR_SIMULATE],
        )

    hass.services.async_register(DOMAIN, SERVICE_SEND_COMMAND, _send_command, schema=SERVICE_SCHEMA)
    return True


async def async_send(
    hass: HomeAssistant,
    entry: PoweroffConfigEntry,
    command: str,
    *,
    warning_seconds: int | None = None,
    message: str | None = None,
    force: bool | None = None,
    simulate: bool = False,
) -> None:
    """Send a command; options of the entry fill what the caller left open."""
    options = entry.options
    if warning_seconds is None:
        warning_seconds = int(options.get(CONF_WARNING_SECONDS, 0))
    if message is None:
        message = options.get(CONF_WARNING_MESSAGE) or None
    if force is None:
        force = bool(options.get(CONF_FORCE, False))
    try:
        await entry.runtime_data.client.async_send_command(
            command,
            warning_seconds=warning_seconds,
            message=message,
            force=force,
            simulate=simulate,
        )
    except PoweroffAuthError as err:
        entry.async_start_reauth(hass)
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
            translation_placeholders={"name": entry.title},
        ) from err
    except PoweroffConnectionError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"name": entry.title, "error": str(err)},
        ) from err
    except PoweroffCommandError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"name": entry.title, "error": str(err)},
        ) from err
    _LOGGER.info("%s: %s sent%s", entry.title, command, " (simulated)" if simulate else "")


async def async_setup_entry(hass: HomeAssistant, entry: PoweroffConfigEntry) -> bool:
    """Set up one Poweroff machine."""
    client = PoweroffClient(
        entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data.get(CONF_PASSWORD)
    )

    async def _update() -> bool:
        return await client.async_is_reachable()

    coordinator: DataUpdateCoordinator[bool] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=f"{DOMAIN} {entry.title}",
        update_method=_update,
        update_interval=SCAN_INTERVAL,
    )
    # Offline machines are normal (they are switched off): no ConfigEntryNotReady.
    await coordinator.async_refresh()
    entry.runtime_data = PoweroffData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PoweroffConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
