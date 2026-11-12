"""Tests for the Poweroff integration against a fake Poweroff server."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.poweroff.client import (
    PoweroffAuthError,
    PoweroffClient,
    PoweroffConnectionError,
)
from custom_components.poweroff.const import DOMAIN

from .conftest import FakePoweroff


def _entry(
    server: FakePoweroff, options: dict | None = None, password: str = "geheim"
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="P5Q-Deluxe",
        unique_id=f"127.0.0.1:{server.port}",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: server.port, CONF_PASSWORD: password},
        options=options or {},
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


# ---------- client ----------


async def test_client_shutdown_lines(poweroff_server: FakePoweroff) -> None:
    client = PoweroffClient("127.0.0.1", poweroff_server.port, "geheim")
    await client.async_send_command("shutdown")
    assert poweroff_server.received[-1] == [
        "PASSWORD geheim",
        "WHO local",
        "WHEN immediate",
        "ACTION shutdown",
        "SIMULATE off",
        "FORCE off",
        "WARNING off",
        "DOIT",
        "QUIT",
    ]


async def test_client_warning_umlauts_and_newline(poweroff_server: FakePoweroff) -> None:
    client = PoweroffClient("127.0.0.1", poweroff_server.port, "geheim")
    await client.async_send_command(
        "standby",
        warning_seconds=60,
        message="Gleich geht's los!\nTschüß",
        force=True,
        simulate=True,
    )
    lines = poweroff_server.received[-1]
    assert "WARNING on" in lines and "WARNTIME 60" in lines
    assert "MESSAGE Gleich geht's los!\\nTschüß" in lines  # cp1252 round trip, \n literal
    assert "FORCE on" in lines and "SIMULATE on" in lines and "ACTION standby" in lines


async def test_client_wrong_password(poweroff_server: FakePoweroff) -> None:
    client = PoweroffClient("127.0.0.1", poweroff_server.port, "falsch")
    with pytest.raises(PoweroffAuthError):
        await client.async_send_command("shutdown")
    assert "DOIT" not in poweroff_server.received[-1]


async def test_client_unreachable_retries(socket_enabled) -> None:
    client = PoweroffClient("127.0.0.1", 1, "x", timeout=1, attempts=2, retry_delay=0)
    with pytest.raises(PoweroffConnectionError):
        await client.async_send_command("shutdown")


async def test_client_reachable(poweroff_server: FakePoweroff) -> None:
    assert await PoweroffClient("127.0.0.1", poweroff_server.port, None).async_is_reachable()
    assert not await PoweroffClient("127.0.0.1", 1, None, timeout=1).async_is_reachable()


# ---------- config flow ----------


async def test_flow_success(hass: HomeAssistant, poweroff_server: FakePoweroff) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "P5Q-Deluxe",
            CONF_HOST: "127.0.0.1",
            CONF_PORT: poweroff_server.port,
            CONF_PASSWORD: "geheim",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "P5Q-Deluxe"
    assert result["data"][CONF_PASSWORD] == "geheim"
    # the check must not change anything on the machine
    assert all("DOIT" not in s for s in poweroff_server.received)


async def test_flow_errors(hass: HomeAssistant, poweroff_server: FakePoweroff) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: poweroff_server.port, CONF_PASSWORD: "falsch"},
    )
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_PASSWORD: "geheim"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_flow_duplicate(hass: HomeAssistant, poweroff_server: FakePoweroff) -> None:
    _entry(poweroff_server).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: poweroff_server.port, CONF_PASSWORD: "geheim"},
    )
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, poweroff_server: FakePoweroff) -> None:
    entry = _entry(poweroff_server)
    await _setup(hass, entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"warning_seconds": 60.0, "warning_message": "Gleich", "force": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"warning_seconds": 60, "warning_message": "Gleich", "force": True}


# ---------- entities ----------


async def test_entities_and_button(hass: HomeAssistant, poweroff_server: FakePoweroff) -> None:
    entry = _entry(
        poweroff_server,
        options={"warning_seconds": 30, "warning_message": "Achtung", "force": False},
    )
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.p5q_deluxe_poweroff_reachable").state == "on"
    for key in ("shut_down", "restart", "standby", "hibernate", "lock"):
        assert hass.states.get(f"button.p5q_deluxe_{key}") is not None, key
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.p5q_deluxe_shut_down"}, blocking=True
    )
    lines = poweroff_server.sessions_with("DOIT")[-1]
    assert "ACTION shutdown" in lines and "WARNTIME 30" in lines and "MESSAGE Achtung" in lines


async def test_offline_machine_loads_and_shows_off(
    hass: HomeAssistant, poweroff_server: FakePoweroff
) -> None:
    entry = _entry(poweroff_server)
    await poweroff_server.stop()
    await _setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.p5q_deluxe_poweroff_reachable").state == "off"
    assert hass.states.get("button.p5q_deluxe_shut_down").state != "unavailable"


async def test_send_command_action(hass: HomeAssistant, poweroff_server: FakePoweroff) -> None:
    entry = _entry(poweroff_server, options={"warning_seconds": 30})
    await _setup(hass, entry)
    await hass.services.async_call(
        DOMAIN,
        "send_command",
        {
            "config_entry_id": entry.entry_id,
            "command": "reboot",
            "warning_seconds": 0,
            "simulate": True,
        },
        blocking=True,
    )
    lines = poweroff_server.sessions_with("DOIT")[-1]
    assert "ACTION reboot" in lines and "SIMULATE on" in lines and "WARNING off" in lines


async def test_send_command_errors(hass: HomeAssistant, poweroff_server: FakePoweroff) -> None:
    entry = _entry(poweroff_server, password="falsch")
    await _setup(hass, entry)
    with pytest.raises(HomeAssistantError, match="password|Passwort"):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            {"config_entry_id": entry.entry_id, "command": "shutdown"},
            blocking=True,
        )
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            {"config_entry_id": "gibtsnicht", "command": "shutdown"},
            blocking=True,
        )
    poweroff_server.reject["doit"] = "Nothing to do"
    entry2 = _entry(poweroff_server)
    entry2._unique_id = "anders"  # noqa: SLF001
    await _setup(hass, entry2)
    with pytest.raises(HomeAssistantError, match="Nothing to do"):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            {"config_entry_id": entry2.entry_id, "command": "lock"},
            blocking=True,
        )


async def test_unload(hass: HomeAssistant, poweroff_server: FakePoweroff) -> None:
    entry = _entry(poweroff_server)
    await _setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_client_name_with_ipv6_and_ipv4(poweroff_server: FakePoweroff) -> None:
    """localhost resolves to ::1 (nobody listening) and 127.0.0.1 -> must still work."""
    client = PoweroffClient("localhost", poweroff_server.port, "geheim", timeout=5)
    await client.async_send_command("lock")
    assert "ACTION lock" in poweroff_server.received[-1]


async def test_flow_add_offline(hass: HomeAssistant, socket_enabled) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    data = {CONF_NAME: "HP-Book", CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_PASSWORD: "x"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["errors"] == {"base": "cannot_connect"}
    assert "add_offline" in result["data_schema"].schema
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**data, "add_offline": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "add_offline" not in result["data"]
