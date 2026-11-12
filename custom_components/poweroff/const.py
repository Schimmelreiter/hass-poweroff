"""Constants for the Poweroff integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "poweroff"

DEFAULT_PORT: Final = 3210
DEFAULT_TIMEOUT: Final = 10.0
SCAN_INTERVAL: Final = timedelta(seconds=60)

CONF_WARNING_SECONDS: Final = "warning_seconds"
CONF_WARNING_MESSAGE: Final = "warning_message"
CONF_FORCE: Final = "force"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_COMMAND: Final = "command"
ATTR_WARNING_SECONDS: Final = "warning_seconds"
ATTR_MESSAGE: Final = "message"
ATTR_FORCE: Final = "force"
ATTR_SIMULATE: Final = "simulate"

SERVICE_SEND_COMMAND: Final = "send_command"

# Actions understood by Poweroff's remote control (ACTION command).
COMMANDS: Final = (
    "shutdown",
    "poweroff",
    "reboot",
    "standby",
    "hibernate",
    "lock",
    "logoff",
    "monitor_off",
    "monitor_on",
)
