"""Client for Galaxy, the web server StarPilot runs on a comma device.

Galaxy gives any device on the same local network a session without a password:
GET /api/auth/session returns a ``galaxy_session`` cookie that lasts 30 minutes.
Writes must also carry an ``Origin`` header that matches the address used.
Nothing here needs changes on the comma.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import DEFAULT_PORT

REQUEST_TIMEOUT = 10


class GalaxyError(Exception):
    """Base error for Galaxy requests."""


class GalaxyConnectionError(GalaxyError):
    """The comma could not be reached."""


class GalaxyAccessError(GalaxyError):
    """Galaxy refused the request because it does not see a direct local connection."""


class GalaxyApiError(GalaxyError):
    """Galaxy answered with an error."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _error_text(body: Any, status: int) -> str:
    if isinstance(body, dict) and isinstance(body.get("error"), str) and body["error"]:
        return body["error"]
    return f"Galaxy answered with HTTP {status}"


class GalaxyClient:
    """Talks to one comma over its local Galaxy address."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int = DEFAULT_PORT) -> None:
        self._session = session
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._token: str | None = None

    async def _raw(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any, Any]:
        # Galaxy serves only a few connections at once, so never hold one open between polls.
        headers = {"Accept": "application/json", "Connection": "close"}
        if self._token is not None:
            headers["Cookie"] = f"galaxy_session={self._token}"
        if method != "GET":
            headers["Origin"] = self.base_url
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, self.base_url + path, headers=headers, json=payload, allow_redirects=False
                ) as response:
                    try:
                        body = await response.json(content_type=None)
                    except (ValueError, aiohttp.ClientPayloadError):
                        body = None
                    return response.status, body, response.cookies
        except (aiohttp.ClientError, TimeoutError, OSError) as error:
            raise GalaxyConnectionError(str(error) or type(error).__name__) from error

    async def async_authenticate(self) -> None:
        """Get a fresh local session."""
        status, body, cookies = await self._raw("GET", "/api/auth/session")
        if status == 403:
            raise GalaxyAccessError(_error_text(body, status))
        if status != 200 or not isinstance(body, dict):
            raise GalaxyApiError(status, _error_text(body, status))
        cookie = cookies.get("galaxy_session") if cookies is not None else None
        if not body.get("localAccess") or cookie is None:
            raise GalaxyAccessError("Galaxy does not see Home Assistant as a device on its local network")
        self._token = cookie.value

    async def _call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if self._token is None:
            await self.async_authenticate()
        status, body, _ = await self._raw(method, path, payload)
        if status == 401:
            await self.async_authenticate()
            status, body, _ = await self._raw(method, path, payload)
        if status == 403:
            raise GalaxyAccessError(_error_text(body, status))
        if status >= 400:
            raise GalaxyApiError(status, _error_text(body, status))
        return body

    async def async_get(self, path: str) -> Any:
        """Read one Galaxy address."""
        return await self._call("GET", path)

    async def async_set_drive_mode(self, mode: str) -> dict[str, Any]:
        """Set the drive state override: auto, offroad or onroad."""
        status = await self._call("GET", "/api/drive-state/status")
        return await self._call("POST", "/api/drive-state/action", {"mode": mode, "revision": status["revision"]})

    async def async_check_for_updates(self) -> dict[str, Any]:
        """Ask the comma to look for a software update."""
        return await self._call("POST", "/api/software/action", {"action": "check"})

    async def async_search(self, query: str) -> list[dict[str, Any]]:
        """Search for a destination with the comma's own map search."""
        result = await self._call("POST", "/api/navigation/search", {"query": query})
        places = result.get("results") if isinstance(result, dict) else None
        return [place for place in places if isinstance(place, dict)] if isinstance(places, list) else []

    async def async_navigate(self, destination: dict[str, Any]) -> dict[str, Any]:
        """Set the navigation destination (name, latitude, longitude, optional address)."""
        navigation = await self._call("GET", "/api/navigation/status")
        return await self._call(
            "POST",
            "/api/navigation/action",
            {"action": "select", "revision": navigation["revision"], "destination": destination},
        )

    async def async_clear_destination(self) -> dict[str, Any]:
        """Clear the navigation destination."""
        navigation = await self._call("GET", "/api/navigation/status")
        return await self._call("POST", "/api/navigation/action", {"action": "clear", "revision": navigation["revision"]})
