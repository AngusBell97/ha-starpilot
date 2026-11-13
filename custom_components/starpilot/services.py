"""Actions for StarPilot."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_CONFIG_ENTRY_ID, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import GalaxyError
from .const import DOMAIN
from .coordinator import StarPilotCoordinator

SERVICE_NAVIGATE = "navigate"
ATTR_QUERY = "query"
ATTR_ADDRESS = "address"

NAVIGATE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_QUERY): vol.All(cv.string, vol.Length(min=1, max=256)),
        vol.Optional(CONF_NAME): vol.All(cv.string, vol.Length(min=1, max=256)),
        vol.Optional(ATTR_ADDRESS): vol.All(cv.string, vol.Length(max=512)),
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
    }
)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> StarPilotCoordinator:
    entries = hass.config_entries.async_entries(DOMAIN)
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id is not None:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    loaded = [entry for entry in entries if entry.state is ConfigEntryState.LOADED]
    if len(loaded) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_device" if not loaded else "choose_device"
        )
    return loaded[0].runtime_data


async def _navigate(call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(call.hass, call)
    has_place = CONF_LATITUDE in call.data and CONF_LONGITUDE in call.data
    if (ATTR_QUERY in call.data) == has_place:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="destination_required")
    try:
        if has_place:
            destination: dict[str, Any] = {
                "name": call.data.get(CONF_NAME) or f"{call.data[CONF_LATITUDE]:.5f}, {call.data[CONF_LONGITUDE]:.5f}",
                "latitude": call.data[CONF_LATITUDE],
                "longitude": call.data[CONF_LONGITUDE],
            }
            if call.data.get(ATTR_ADDRESS):
                destination["address"] = call.data[ATTR_ADDRESS]
        else:
            places = await coordinator.client.async_search(call.data[ATTR_QUERY])
            if not places:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_search_result",
                    translation_placeholders={"query": call.data[ATTR_QUERY]},
                )
            destination = {
                key: places[0][key] for key in ("name", "latitude", "longitude", "address") if key in places[0]
            }
        await coordinator.client.async_navigate(destination)
    except GalaxyError as error:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="action_failed", translation_placeholders={"error": str(error)}
        ) from error
    coordinator.forget("navigation")
    await coordinator.async_request_refresh()
    return {"destination": destination} if call.return_response else None


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions once for the integration."""
    hass.services.async_register(
        DOMAIN, SERVICE_NAVIGATE, _navigate, schema=NAVIGATE_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
