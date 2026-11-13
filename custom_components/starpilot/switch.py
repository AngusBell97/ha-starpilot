"""Navigation switches for StarPilot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import GalaxyError
from .const import DOMAIN
from .coordinator import StarPilotConfigEntry, StarPilotCoordinator, dig
from .entity import StarPilotEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class StarPilotSwitchDescription(SwitchEntityDescription):
    """A switch and the navigation field it changes."""

    field: str


SWITCHES: tuple[StarPilotSwitchDescription, ...] = (
    StarPilotSwitchDescription(key="navigation_enabled", translation_key="navigation_enabled", field="enabled"),
    StarPilotSwitchDescription(key="slow_for_turns", translation_key="slow_for_turns", field="slowForTurns"),
    StarPilotSwitchDescription(key="avoid_tolls", translation_key="avoid_tolls", field="avoidTolls"),
    StarPilotSwitchDescription(key="avoid_motorways", translation_key="avoid_motorways", field="avoidHighways"),
    StarPilotSwitchDescription(key="avoid_ferries", translation_key="avoid_ferries", field="avoidFerries"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: StarPilotConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the switches Galaxy's navigation status reports."""
    coordinator = entry.runtime_data
    async_add_entities(
        StarPilotSwitch(coordinator, description)
        for description in SWITCHES
        if isinstance(dig(coordinator.data, "navigation", description.field), bool)
    )


class StarPilotSwitch(StarPilotEntity, SwitchEntity):
    """One on/off navigation setting, changed the way Galaxy's own page changes it."""

    entity_description: StarPilotSwitchDescription
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: StarPilotCoordinator, description: StarPilotSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        value = dig(self.coordinator.data, "navigation", self.entity_description.field)
        return value if isinstance(value, bool) else None

    async def _set(self, value: bool) -> None:
        try:
            await self.coordinator.client.async_configure_navigation({self.entity_description.field: value})
        except GalaxyError as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="action_failed", translation_placeholders={"error": str(error)}
            ) from error
        self.coordinator.forget("navigation")
        await self.coordinator.async_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
