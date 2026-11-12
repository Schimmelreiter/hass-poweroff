"""Client for the remote control of Poweroff (Jorgen Bosman), TCP port 3210.

The protocol is line based (CRLF). On connect the server greets with
``201 Welcome to Poweroff <version> ...``. Every command is answered with
``250 OK``, ``201 <info>`` lines or ``501 <error>``. Poweroff serves one client
at a time; a new connection closes the previous one.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .const import COMMANDS, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)

CODE_INFO = "201"
CODE_OK = "250"
CODE_ERROR = "501"
ENCODING = "cp1252"  # Poweroff is a Windows ANSI program


class PoweroffError(Exception):
    """Base error."""


class PoweroffConnectionError(PoweroffError):
    """Poweroff is not reachable or the connection broke."""


class PoweroffAuthError(PoweroffError):
    """The password was rejected."""


class PoweroffCommandError(PoweroffError):
    """Poweroff rejected a command."""


@dataclass(slots=True)
class PoweroffInfo:
    """What the greeting tells about the server."""

    version: str | None


class PoweroffClient:
    """Talk to one Poweroff instance."""

    def __init__(
        self,
        host: str,
        port: int,
        password: str | None,
        timeout: float = DEFAULT_TIMEOUT,
        attempts: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        """Store the connection data."""
        self.host = host
        self.port = port
        self._password = password or ""
        self._timeout = timeout
        self._attempts = attempts
        self._retry_delay = retry_delay
        self._lock = asyncio.Lock()
        # Original Poweroff (3.0.1.x) listens on IPv4 only; a name that also resolves to IPv6
        # then hangs there. Happy eyeballs tries the next address after 0.3 s, so IPv4 and
        # Poweroff 3.0.2 (IPv6) both work.

    async def _read_line(self, reader: asyncio.StreamReader) -> str:
        try:
            raw = await asyncio.wait_for(reader.readline(), self._timeout)
        except TimeoutError as err:
            raise PoweroffConnectionError("No answer from Poweroff") from err
        if not raw:
            raise PoweroffConnectionError("Connection closed by Poweroff")
        return raw.decode(ENCODING, errors="replace").strip()

    async def _send(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, line: str
    ) -> str:
        """Send one command and return the final answer (250 ... or 501 ...)."""
        writer.write(line.encode(ENCODING, errors="replace") + b"\r\n")
        await writer.drain()
        while True:
            answer = await self._read_line(reader)
            if answer.startswith((CODE_OK, CODE_ERROR)):
                return answer
            # 201 lines are informational (e.g. after VERSION); VERSION ends with one
            if line.upper() == "VERSION" and answer.startswith(CODE_INFO):
                return answer

    async def _session(self, commands: list[str]) -> PoweroffInfo:
        """Connect, authenticate, run the commands, disconnect."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, happy_eyeballs_delay=0.3),
                self._timeout,
            )
        except (OSError, TimeoutError) as err:
            raise PoweroffConnectionError(
                f"Cannot connect to {self.host}:{self.port}: {err}"
            ) from err
        try:
            greeting = await self._read_line(reader)
            if not greeting.startswith(CODE_INFO) or "Poweroff" not in greeting:
                raise PoweroffConnectionError(f"Unexpected greeting: {greeting!r}")
            parts = greeting.split()
            info = PoweroffInfo(
                version=parts[4] if len(parts) > 4 and parts[3] == "Poweroff" else None
            )
            if self._password:
                answer = await self._send(reader, writer, f"PASSWORD {self._password}")
                if not answer.startswith(CODE_OK):
                    raise PoweroffAuthError(answer[4:] or "Invalid password")
            for command in commands:
                answer = await self._send(reader, writer, command)
                if answer.startswith(CODE_ERROR):
                    if "Access is denied" in answer:
                        raise PoweroffAuthError(answer[4:])
                    shown = command.split(" ", 1)[0]
                    raise PoweroffCommandError(f"{shown}: {answer[4:]}")
            try:
                writer.write(b"QUIT\r\n")
                await writer.drain()
                await asyncio.wait_for(reader.readline(), 2)  # "201 Bye bye"
            except (OSError, TimeoutError):
                pass  # e.g. the machine is already going down
            return info
        except OSError as err:
            raise PoweroffConnectionError(str(err)) from err
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except (OSError, TimeoutError):
                pass

    async def _run(self, commands: list[str]) -> PoweroffInfo:
        """Run a session, retrying connection problems (not auth/command errors)."""
        async with self._lock:
            for attempt in range(1, self._attempts + 1):
                try:
                    return await self._session(commands)
                except PoweroffConnectionError as err:
                    if attempt == self._attempts:
                        raise
                    _LOGGER.debug("Attempt %s to reach %s failed: %s", attempt, self.host, err)
                    await asyncio.sleep(self._retry_delay)
        raise PoweroffConnectionError("unreachable")  # pragma: no cover

    async def async_check(self) -> PoweroffInfo:
        """Connect and authenticate (used by the config flow)."""
        return await self._run([])

    async def async_is_reachable(self) -> bool:
        """Return whether Poweroff answers (one attempt, no password needed)."""
        try:
            async with self._lock:
                await self._session_greeting_only()
        except PoweroffError:
            return False
        return True

    async def _session_greeting_only(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, happy_eyeballs_delay=0.3),
                self._timeout,
            )
        except (OSError, TimeoutError) as err:
            raise PoweroffConnectionError(str(err)) from err
        try:
            greeting = await self._read_line(reader)
            if not greeting.startswith(CODE_INFO):
                raise PoweroffConnectionError(f"Unexpected greeting: {greeting!r}")
            writer.write(b"QUIT\r\n")
            await writer.drain()
        except OSError as err:
            raise PoweroffConnectionError(str(err)) from err
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except (OSError, TimeoutError):
                pass

    async def async_send_command(
        self,
        command: str,
        *,
        warning_seconds: int = 0,
        message: str | None = None,
        force: bool = False,
        simulate: bool = False,
    ) -> None:
        """Let Poweroff perform an action on its own machine, right now."""
        if command not in COMMANDS:
            raise PoweroffCommandError(f"Unknown command {command!r}")
        lines = [
            "WHO local",
            "WHEN immediate",
            f"ACTION {command}",
            f"SIMULATE {'on' if simulate else 'off'}",
            f"FORCE {'on' if force else 'off'}",
        ]
        if warning_seconds > 0:
            lines += ["WARNING on", f"WARNTIME {int(warning_seconds)}"]
            text = (message or "").replace("\r\n", "\n").replace("\n", "\\n")
            lines.append(f"MESSAGE {text}" if text else "MESSAGE")
        else:
            lines.append("WARNING off")
        lines.append("DOIT")
        await self._run(lines)
