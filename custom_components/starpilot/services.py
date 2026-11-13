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
SERVICE_GET_SETTINGS = "get_settings"
SERVICE_SET_SETTING = "set_setting"
ATTR_PAGE = "page"
ATTR_SETTING = "setting"
ATTR_VALUE = "value"
ROW_FIELDS = ("label", "value", "choices", "minimum", "maximum", "step", "unit", "available", "reason")
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


PAGE = vol.All(cv.string, vol.Length(min=1, max=64), vol.Match(r"^[a-z_]+(/[a-z_]+)?$"))
GET_SETTINGS_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string, vol.Required(ATTR_PAGE): PAGE})
SET_SETTING_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_PAGE): PAGE,
        vol.Required(ATTR_SETTING): vol.All(cv.string, vol.Length(min=1, max=128)),
        vol.Required(ATTR_VALUE): vol.Any(bool, int, float, vol.All(cv.string, vol.Length(min=1, max=128))),
    }
)


def _failed(error: GalaxyError) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN, translation_key="action_failed", translation_placeholders={"error": str(error)}
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
    await coordinator.async_refresh()
    return {"destination": destination} if call.return_response else None


async def _get_settings(call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(call.hass, call)
    try:
        page = await coordinator.client.async_settings_page(call.data[ATTR_PAGE])
    except GalaxyError as error:
        raise _failed(error) from error
    rows = page.get("rows") if isinstance(page, dict) else None
    settings = []
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        entry: dict[str, Any] = {key: row[key] for key in ROW_FIELDS if row.get(key) not in (None, "", [])}
        if row.get("page"):
            entry["opens_page"] = row["page"]
        settings.append(entry)
    return {"page": page.get("page"), "title": page.get("title"), "parked": page.get("parked"), "settings": settings}


async def _set_setting(call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(call.hass, call)
    value = call.data[ATTR_VALUE]
    if isinstance(value, bool):
        value = "On" if value else "Off"
    try:
        result = await coordinator.client.async_set_setting(call.data[ATTR_PAGE], call.data[ATTR_SETTING], value)
    except GalaxyError as error:
        raise _failed(error) from error
    coordinator.forget("changed")
    await coordinator.async_refresh()
    return result if call.return_response else None


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions once for the integration."""
    hass.services.async_register(
        DOMAIN, SERVICE_NAVIGATE, _navigate, schema=NAVIGATE_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_SETTINGS, _get_settings, schema=GET_SETTINGS_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SETTING, _set_setting, schema=SET_SETTING_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
