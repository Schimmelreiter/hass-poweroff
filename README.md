# Poweroff for Home Assistant

Shut down, restart, put to standby, hibernate or lock Windows machines from Home Assistant –
through the remote control of Poweroff by Jorgen Bosman
(TCP port 3210). This replaces `telnet` scripts in `shell_command`.

## Requirements

- Poweroff running on the Windows machine (as a program or service) with **remote control**
  enabled; note the port (default 3210) and the password.
- The machine reachable from Home Assistant on that port. The original Poweroff (3.0.1.x)
  listens on IPv4 only, [Poweroff 3.0.2](https://github.com/Schimmelreiter/poweroff) also on
  IPv6. For names with both addresses the integration tries them in parallel (happy eyeballs),
  so either version works.

## Installation

Marketplace (formerly HACS): add this repository as a custom repository of type
*Integration*, install **Poweroff**, restart Home Assistant.

Manual: copy `custom_components/poweroff` into your `config/custom_components`, restart.

## Setup

*Settings → Devices & services → Add integration → Poweroff*, one entry per machine:
name, host, port, password. The connection and the password are checked right away
(nothing is executed on the machine).

Options per machine (used by the buttons): warning in seconds before the action with a
text shown on the machine, and whether programs are forced to close.

## Entities

| Entity | Description |
| --- | --- |
| Binary sensor *Poweroff reachable* | On while Poweroff answers (polled every 60 s). |
| Buttons *Shut down*, *Restart*, *Standby*, *Hibernate*, *Lock* | Send the action right away. |

*Shut down* sends Poweroff's `shutdown`, i.e. what Windows does on shutdown (with fast
startup that is a hybrid shutdown that Wake-on-LAN can usually wake). A complete power
off is only available as `poweroff` through the action below.

## Action `poweroff.send_command`

```yaml
action: poweroff.send_command
data:
  config_entry_id: 01ABC...        # the machine
  command: standby                 # shutdown, poweroff, reboot, standby, hibernate,
                                   # lock, logoff, monitor_off, monitor_on
  warning_seconds: 60              # optional, overrides the option of the entry
  message: "Shutting down in one minute!"
  force: false
  simulate: false                  # true: Poweroff only shows what it would do
```

`simulate: true` opens a window on the machine that has to be closed – until then it
blocks the next shutdown.

A Wake-on-LAN switch can combine both, e.g. a template switch with
`turn_on: wake_on_lan.send_magic_packet` and `turn_off: button.press` of a Poweroff button.

## Protocol

Line based, CRLF. Greeting `201 Welcome to Poweroff <version> ...`; answers `250 OK`,
`201 <info>` or `501 <error>`. The integration sends `PASSWORD`, `WHO local`,
`WHEN immediate`, `ACTION`, `SIMULATE`, `FORCE`, `WARNING`/`WARNTIME`/`MESSAGE`, `DOIT`,
`QUIT`. Poweroff serves one client at a time; connection errors are retried.

## License

MIT
