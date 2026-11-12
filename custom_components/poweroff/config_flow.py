"""Config flow for Poweroff."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import PoweroffAuthError, PoweroffClient, PoweroffConnectionError
from .const import (
    CONF_ADD_OFFLINE,
    CONF_FORCE,
    CONF_WARNING_MESSAGE,
    CONF_WARNING_SECONDS,
    DEFAULT_PORT,
    DOMAIN,
)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _validate(host: str, port: int, password: str | None) -> dict[str, str]:
    """Return errors for the form (empty if fine)."""
    client = PoweroffClient(host, port, password, attempts=1)
    try:
        await client.async_check()
    except PoweroffAuthError:
        return {"base": "invalid_auth"}
    except PoweroffConnectionError:
        return {"base": "cannot_connect"}
    return {}


class PoweroffConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a machine running Poweroff."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for name, host, port and password."""
        errors: dict[str, str] = {}
        offline = False
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            # a form left open (e.g. "machine is off") must not block a new attempt
            await self.async_set_unique_id(f"{host.lower()}:{port}", raise_on_progress=False)
            self._abort_if_unique_id_configured()
            if user_input.get(CONF_ADD_OFFLINE):
                errors = {}  # machine is off: password is checked on the first use
            else:
                errors = await _validate(host, port, user_input.get(CONF_PASSWORD))
            if not errors:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or host,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_PASSWORD: user_input.get(CONF_PASSWORD, ""),
                    },
                )
            offline = errors.get("base") == "cannot_connect"
        fields: dict[Any, Any] = {
            vol.Optional(CONF_NAME): str,
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Optional(CONF_PASSWORD): PASSWORD_SELECTOR,
        }
        if offline:
            # switched-off machines can be added without the check
            fields[vol.Optional(CONF_ADD_OFFLINE, default=False)] = bool
        schema = vol.Schema(fields)
        shown = {k: v for k, v in (user_input or {}).items() if k != CONF_ADD_OFFLINE}
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, shown),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The password was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input.get(CONF_PASSWORD, "")
            errors = await _validate(entry.data[CONF_HOST], entry.data[CONF_PORT], password)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Warning and force settings."""
        return PoweroffOptionsFlow()


class PoweroffOptionsFlow(OptionsFlow):
    """Warning before the action, force closing programs."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            user_input[CONF_WARNING_SECONDS] = int(user_input.get(CONF_WARNING_SECONDS, 0))
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(CONF_WARNING_SECONDS, default=0): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=3600,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(CONF_WARNING_MESSAGE): TextSelector(
                    TextSelectorConfig(multiline=True)
                ),
                vol.Required(CONF_FORCE, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, dict(self.config_entry.options)
            ),
        )
