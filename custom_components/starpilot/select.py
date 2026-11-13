"""The drive state override: let the comma decide, or force it offroad or onroad."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import GalaxyError
from .const import DOMAIN, DRIVE_MODES
from .coordinator import StarPilotConfigEntry, StarPilotCoordinator, dig
from .entity import StarPilotEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: StarPilotConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the drive state select."""
    async_add_entities([DriveModeSelect(entry.runtime_data)])


class DriveModeSelect(StarPilotEntity, SelectEntity):
    """Mirrors Galaxy's own Auto / Offroad / Onroad control; Galaxy applies its own safety checks."""

    _attr_translation_key = "drive_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(DRIVE_MODES)

    def __init__(self, coordinator: StarPilotCoordinator) -> None:
        super().__init__(coordinator, "drive_mode")

    @property
    def available(self) -> bool:
        return super().available and dig(self.coordinator.data, "drive_state", "available") is True

    @property
    def current_option(self) -> str | None:
        mode = dig(self.coordinator.data, "drive_state", "mode")
        return mode if mode in DRIVE_MODES else None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        attributes = {
            "effective": dig(self.coordinator.data, "drive_state", "effective"),
            "reason": dig(self.coordinator.data, "drive_state", "reason"),
        }
        return {key: value for key, value in attributes.items() if value is not None}

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.client.async_set_drive_mode(option)
        except GalaxyError as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="action_failed", translation_placeholders={"error": str(error)}
            ) from error
        await self.coordinator.async_refresh()
