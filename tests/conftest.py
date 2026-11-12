"""Fixtures: a fake Poweroff server speaking the remote control protocol."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/poweroff."""
    yield


class FakePoweroff:
    """Minimal Poweroff remote control (one client at a time, like the original)."""

    def __init__(self, password: str = "geheim") -> None:
        self.password = password
        self.received: list[list[str]] = []  # commands per connection
        self.reject: dict[str, str] = {}  # command -> error text
        self.server: asyncio.base_events.Server | None = None
        self.port = 0

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        lines: list[str] = []
        self.received.append(lines)
        authenticated = not self.password
        writer.write(b"201 Welcome to Poweroff 3.0.1 created by Jorgen Bosman\r\n")
        await writer.drain()
        while raw := await reader.readline():
            line = raw.decode("cp1252").rstrip("\r\n")
            lines.append(line)
            command, _, value = line.partition(" ")
            cmd = command.lower()
            if cmd == "quit":
                writer.write(b"201 Bye bye\r\n")
                break
            if cmd == "password":
                if value == self.password:
                    authenticated = True
                    writer.write(b"250 OK\r\n")
                else:
                    writer.write(b"501 Invalid password\r\n")
            elif cmd == "version":
                writer.write(b"201 3.0.1\r\n")
            elif not authenticated:
                writer.write(b"501 Access is denied\r\n")
                await writer.drain()
                break
            elif cmd in self.reject:
                writer.write(f"501 {self.reject[cmd]}\r\n".encode())
            else:
                writer.write(b"250 OK\r\n")
            await writer.drain()
        writer.close()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    def sessions_with(self, word: str) -> list[list[str]]:
        return [s for s in self.received if any(word in line for line in s)]


@pytest.fixture
async def poweroff_server(socket_enabled) -> AsyncGenerator[FakePoweroff]:
    """Run a fake Poweroff server."""
    server = FakePoweroff()
    await server.start()
    yield server
    await server.stop()
