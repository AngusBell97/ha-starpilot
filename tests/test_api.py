"""The Galaxy client against a small server that enforces Galaxy's own access rules."""

from __future__ import annotations

from collections.abc import Generator
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any

import aiohttp
import pytest

from custom_components.starpilot.api import GalaxyAccessError, GalaxyApiError, GalaxyClient, GalaxyConnectionError


class MiniGalaxy(ThreadingHTTPServer):
    """Mirrors server.py: Host must be the socket address, writes need a matching Origin, reads need a session."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), MiniHandler)
        self.sessions: set[str] = set()
        self.issued = 0
        self.requests: list[tuple[str, str, dict[str, str], Any]] = []
        self.local = True
        self.mode = "auto"


class MiniHandler(BaseHTTPRequestHandler):
    server: MiniGalaxy
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: Any) -> None:
        pass

    def reply(self, status: int, body: Any, cookie: str | None = None) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        if self.close_connection:
            # Galaxy says so too (http_server.py end_headers); without it the client would reuse a dead connection.
            self.send_header("Connection", "close")
        if cookie is not None:
            self.send_header("Set-Cookie", f"galaxy_session={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=1800")
        self.end_headers()
        self.wfile.write(raw)

    def token(self) -> str | None:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        return cookie["galaxy_session"].value if "galaxy_session" in cookie else None

    def allowed(self, mutation: bool) -> bool:
        host, origin = self.headers.get("Host", ""), self.headers.get("Origin")
        address, port = self.server.server_address[:2]
        if host != f"{address}:{port}" or (mutation and origin != f"http://{host}") or \
           (origin is not None and origin != f"http://{host}"):
            self.reply(403, {"error": "Local access only"})
            return False
        return True

    def do_GET(self) -> None:
        self.server.requests.append(("GET", self.path, dict(self.headers), None))
        if not self.allowed(False):
            return
        if self.path == "/api/auth/session":
            if not self.server.local:
                self.reply(200, {"authenticated": False, "localAccess": False, "state": "setup_required"})
                return
            self.server.issued += 1
            token = f"token-{self.server.issued}"
            self.server.sessions.add(token)
            self.reply(200, {"authenticated": True, "state": "configured", "localAccess": True}, cookie=token)
        elif self.token() not in self.server.sessions:
            self.reply(401, {"error": "Refresh the local Galaxy session"})
        elif self.path == "/api/device/state":
            self.reply(200, {"state": "parked", "maxAgeMs": 3000})
        elif self.path == "/api/drive-state/status":
            self.reply(200, {"mode": self.server.mode, "revision": "r" * 32, "available": True})
        elif self.path == "/api/weather":
            self.reply(503, {"error": "Weather is unavailable"})
        else:
            self.reply(404, {"error": "Capability unavailable"})

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size)) if size else None
        self.server.requests.append(("POST", self.path, dict(self.headers), payload))
        if not self.allowed(True):
            return
        if self.token() not in self.server.sessions:
            self.reply(401, {"error": "Sign in to Galaxy"})
        elif self.headers.get("Transfer-Encoding") is not None or \
                self.headers.get("Content-Type", "").lower() != "application/json":
            self.reply(415, {"error": "JSON required"})
        elif self.path == "/api/drive-state/action" and set(payload) == {"mode", "revision"} and payload["revision"] == "r" * 32:
            self.server.mode = payload["mode"]
            self.reply(200, {"mode": self.server.mode, "revision": "s" * 32, "available": True})
        else:
            self.reply(400, {"error": "Invalid request"})


@pytest.fixture
def mini(socket_enabled: None) -> Generator[MiniGalaxy]:
    server = MiniGalaxy()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _client(session: aiohttp.ClientSession, server: MiniGalaxy) -> GalaxyClient:
    return GalaxyClient(session, "127.0.0.1", server.server_address[1])


async def test_read_gets_a_session_first(mini: MiniGalaxy) -> None:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        client = _client(session, mini)
        assert await client.async_get("/api/device/state") == {"state": "parked", "maxAgeMs": 3000}
        assert await client.async_get("/api/device/state") == {"state": "parked", "maxAgeMs": 3000}
    assert [path for _, path, _, _ in mini.requests] == ["/api/auth/session", "/api/device/state", "/api/device/state"]
    assert mini.issued == 1
    # No connection is held open between polls.
    assert all(headers.get("Connection") == "close" for _, _, headers, _ in mini.requests)


async def test_expired_session_is_renewed(mini: MiniGalaxy) -> None:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        client = _client(session, mini)
        await client.async_get("/api/device/state")
        mini.sessions.clear()  # Galaxy restarted, or 30 minutes passed.
        assert (await client.async_get("/api/device/state"))["state"] == "parked"
    assert mini.issued == 2


async def test_write_carries_origin_and_revision(mini: MiniGalaxy) -> None:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        client = _client(session, mini)
        result = await client.async_set_drive_mode("offroad")
    assert result["mode"] == "offroad" and mini.mode == "offroad"
    method, path, headers, payload = mini.requests[-1]
    assert (method, path) == ("POST", "/api/drive-state/action")
    assert headers["Origin"] == f"http://127.0.0.1:{mini.server_address[1]}"
    assert headers["Content-Type"] == "application/json" and "Transfer-Encoding" not in headers
    assert payload == {"mode": "offroad", "revision": "r" * 32}


async def test_errors(mini: MiniGalaxy) -> None:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        client = _client(session, mini)
        with pytest.raises(GalaxyApiError, match="Weather is unavailable") as raised:
            await client.async_get("/api/weather")
        assert raised.value.status == 503

        # A hostname Galaxy does not know is refused, as on the real server.
        named = GalaxyClient(session, "localhost", mini.server_address[1])
        with pytest.raises(GalaxyAccessError, match="Local access only"):
            await named.async_get("/api/device/state")

        mini.local = False
        with pytest.raises(GalaxyAccessError, match="local network"):
            await _client(session, mini).async_get("/api/device/state")


async def test_unreachable(socket_enabled: None) -> None:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        with pytest.raises(GalaxyConnectionError):
            await GalaxyClient(session, "127.0.0.1", 9).async_get("/api/device/state")
