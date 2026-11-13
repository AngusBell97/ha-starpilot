"""Shared test setup: a comma whose Galaxy replies come from galaxy_data."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.starpilot.api import GalaxyApiError, GalaxyClient
from custom_components.starpilot.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .galaxy_data import replies


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components."""


class FakeGalaxy:
    """Stands in for the comma: answers reads from a dict and records writes."""

    def __init__(self) -> None:
        self.replies: dict[str, Any] = replies()
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.search_results: list[dict[str, Any]] = [
            {"id": "abc", "name": "Bristol Airport", "address": "Bristol BS48 3DY", "latitude": 51.38, "longitude": -2.71}
        ]
        self.error: Exception | None = None
        self.pending: tuple[int, Any] = (0, None)

    async def call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if self.error is not None:
            raise self.error
        if method == "GET":
            if path not in self.replies:
                raise GalaxyApiError(404, "Capability unavailable")
            return self.replies[path]
        assert payload is not None
        self.posts.append((path, payload))
        if path == "/api/navigation/search":
            return {"results": self.search_results}
        if path == "/api/navigation/action" and payload["action"] == "configure":
            self.replies["/api/navigation/status"].update(payload["patch"])
            return self.replies["/api/navigation/status"]
        if path == "/api/settings/preview":
            row = self.replies["/api/settings/pages/sounds"]["rows"][payload["row"]]
            if payload["value"] not in row["choices"]:
                raise GalaxyApiError(409, "Saved settings changed; refresh the page")
            self.pending = (payload["row"], payload["value"])
            return {"intent": "intent-1", "question": "Change it?", "proposed": payload["value"]}
        if path == "/api/settings/confirm":
            index, value = self.pending
            self.replies["/api/settings/pages/sounds"]["rows"][index]["value"] = value
            return {"saved": True}
        if path == "/api/navigation/action":
            navigation = self.replies["/api/navigation/status"]
            navigation["destination"] = payload.get("destination") if payload["action"] == "select" else None
            navigation["status"] = "waitingForLocation" if payload["action"] == "select" else "noDestination"
            return navigation
        if path == "/api/drive-state/action":
            self.replies["/api/drive-state/status"]["mode"] = payload["mode"]
            return self.replies["/api/drive-state/status"]
        return {}


@pytest.fixture
def galaxy() -> Generator[FakeGalaxy]:
    """Replace the network layer of every GalaxyClient with a FakeGalaxy."""
    fake = FakeGalaxy()

    async def call(self: GalaxyClient, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        return await fake.call(method, path, payload)

    async def authenticate(self: GalaxyClient) -> None:
        if fake.error is not None:
            raise fake.error

    with (
        patch.object(GalaxyClient, "_call", call),
        patch.object(GalaxyClient, "async_authenticate", authenticate),
    ):
        yield fake


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """A comma that is set up but not loaded yet."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="comma four",
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 8082},
        unique_id="thegalaxy-ab12",
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture
async def loaded(hass: HomeAssistant, entry: MockConfigEntry, galaxy: FakeGalaxy) -> MockConfigEntry:
    """A comma that is set up and polled once."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
