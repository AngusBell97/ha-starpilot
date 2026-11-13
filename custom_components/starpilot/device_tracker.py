"""The comma's last known position, from its navigation status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import StarPilotConfigEntry, StarPilotCoordinator, dig
from .entity import StarPilotEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: StarPilotConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the tracker."""
    async_add_entities([StarPilotTracker(entry.runtime_data)])


class StarPilotTracker(StarPilotEntity, TrackerEntity):
    """Galaxy only reports a position while navigation is switched on with a map key."""

    _attr_translation_key = "location"
    _attr_source_type = SourceType.GPS
    # Off until asked for: most cars already have a tracker, and this one only updates on home Wi-Fi.
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: StarPilotCoordinator) -> None:
        super().__init__(coordinator, "location")

    def _coordinate(self, key: str) -> float | None:
        value = dig(self.coordinator.data, "navigation", "location", key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    @property
    def latitude(self) -> float | None:
        return self._coordinate("latitude")

    @property
    def longitude(self) -> float | None:
        return self._coordinate("longitude")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes = {
            "bearing": self._coordinate("bearing"),
            "last_known": dig(self.coordinator.data, "navigation", "location", "lastKnown"),
        }
        return {key: value for key, value in attributes.items() if value is not None}
