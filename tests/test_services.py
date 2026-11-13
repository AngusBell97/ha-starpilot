"""The Set destination action."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.starpilot.api import GalaxyApiError
from custom_components.starpilot.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import FakeGalaxy

REVISION = "fedcba9876543210fedcba9876543210"


async def test_navigate_to_coordinates(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    await hass.services.async_call(
        DOMAIN, "navigate", {"name": "Work", "latitude": 51.5, "longitude": -2.6}, blocking=True
    )
    await hass.async_block_till_done()
    assert galaxy.posts == [
        (
            "/api/navigation/action",
            {"action": "select", "revision": REVISION, "destination": {"name": "Work", "latitude": 51.5, "longitude": -2.6}},
        )
    ]
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{loaded.entry_id}_destination")
    assert hass.states.get(entity_id).state == "Work"


async def test_navigate_by_search(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    response = await hass.services.async_call(
        DOMAIN, "navigate", {"query": "Bristol Airport"}, blocking=True, return_response=True
    )
    assert galaxy.posts[0] == ("/api/navigation/search", {"query": "Bristol Airport"})
    assert galaxy.posts[1][1]["destination"] == {
        "name": "Bristol Airport",
        "address": "Bristol BS48 3DY",
        "latitude": 51.38,
        "longitude": -2.71,
    }
    assert response["destination"]["name"] == "Bristol Airport"


async def test_navigate_needs_one_kind_of_destination(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    for data in ({}, {"name": "Work"}, {"query": "x", "latitude": 1.0, "longitude": 1.0}):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "navigate", data, blocking=True)
    assert galaxy.posts == []


async def test_navigate_no_result(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    galaxy.search_results = []
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "navigate", {"query": "nowhere at all"}, blocking=True)


async def test_navigate_refused(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    galaxy.error = GalaxyApiError(409, "Navigation changed; refresh the page")
    with pytest.raises(HomeAssistantError, match="Navigation changed"):
        await hass.services.async_call(DOMAIN, "navigate", {"latitude": 51.5, "longitude": -2.6}, blocking=True)


async def test_navigate_without_a_comma(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    assert await hass.config_entries.async_unload(loaded.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "navigate", {"latitude": 51.5, "longitude": -2.6}, blocking=True)


async def test_get_settings(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    response = await hass.services.async_call(
        DOMAIN, "get_settings", {"page": "sounds"}, blocking=True, return_response=True
    )
    assert response["title"] == "Sounds & Alerts" and response["parked"] is True
    assert response["settings"][1] == {
        "label": "Engagement Chime",
        "value": "Auto",
        "choices": ["0%", "50%", "Auto"],
        "unit": "%",
        "available": True,
    }
    assert response["settings"][2]["reason"] == "Needs a car"


async def test_set_setting(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    response = await hass.services.async_call(
        DOMAIN, "set_setting", {"page": "sounds", "setting": "engagement chime", "value": "50%"},
        blocking=True, return_response=True,
    )
    assert response == {"setting": "Engagement Chime", "previous": "Auto", "value": "50%"}
    assert galaxy.posts[:2] == [
        ("/api/settings/preview", {"view": "view-1", "row": 1, "value": "50%"}),
        ("/api/settings/confirm", {"intent": "intent-1", "confirmed": True}),
    ]
    assert galaxy.replies["/api/settings/pages/sounds"]["rows"][1]["value"] == "50%"


async def test_set_setting_refusals(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    for data, message in (
        ({"page": "sounds", "setting": "No such thing", "value": "On"}, "no setting called"),
        ({"page": "sounds", "setting": "Locked", "value": True}, "cannot be changed"),
        ({"page": "sounds", "setting": "Engagement Chime", "value": "11%"}, "Saved settings changed"),
        ({"page": "nowhere", "setting": "x", "value": "On"}, "Capability unavailable"),
    ):
        with pytest.raises(HomeAssistantError, match=message):
            await hass.services.async_call(DOMAIN, "set_setting", data, blocking=True)
    assert not any(path == "/api/settings/confirm" for path, _ in galaxy.posts)
    with pytest.raises(Exception):  # noqa: B017, PT011 - schema rejects a page that is not an ID
        await hass.services.async_call(DOMAIN, "set_setting", {"page": "../auth", "setting": "x", "value": "On"}, blocking=True)
