"""Diagnostics download for StarPilot."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import StarPilotConfigEntry

TO_REDACT = {
    CONF_HOST,
    "latitude",
    "longitude",
    "location",
    "destination",
    "recents",
    "favorites",
    "route",
    "alternatives",
    "address",
    "routeId",
    "instance",
    "sourceId",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: StarPilotConfigEntry) -> dict[str, Any]:
    """Return the last Galaxy poll with places and addresses removed."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
