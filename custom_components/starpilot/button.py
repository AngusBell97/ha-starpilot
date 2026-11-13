"""Buttons for StarPilot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import GalaxyClient, GalaxyError
from .const import DOMAIN
from .coordinator import StarPilotConfigEntry, StarPilotCoordinator, external_gpu
from .entity import StarPilotEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class StarPilotButtonDescription(ButtonEntityDescription):
    """A button, what it asks Galaxy to do, and what to read again afterwards."""

    press_fn: Callable[[GalaxyClient], Awaitable[Any]]
    refresh: tuple[str, ...]


BUTTONS: tuple[StarPilotButtonDescription, ...] = (
    StarPilotButtonDescription(
        key="clear_destination",
        translation_key="clear_destination",
        press_fn=lambda client: client.async_clear_destination(),
        refresh=("navigation",),
    ),
    StarPilotButtonDescription(
        key="check_for_updates",
        translation_key="check_for_updates",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.async_check_for_updates(),
        refresh=("software",),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: StarPilotConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the buttons."""
    coordinator = entry.runtime_data
    async_add_entities(StarPilotButton(coordinator, description) for description in BUTTONS)
    gpu = external_gpu(coordinator.data)
    if gpu is not None and gpu.get("peaksResettable") is True and isinstance(gpu.get("kind"), str):
        kind, name = gpu["kind"], gpu.get("name")
        async_add_entities(
            [
                StarPilotButton(
                    coordinator,
                    StarPilotButtonDescription(
                        key="reset_external_gpu_peaks",
                        translation_key="reset_external_gpu_peaks",
                        entity_category=EntityCategory.CONFIG,
                        press_fn=lambda client: client.async_reset_gpu_peaks(kind),
                        refresh=("monitor",),
                    ),
                    {"gpu": name if isinstance(name, str) and name else "External GPU"},
                )
            ]
        )


class StarPilotButton(StarPilotEntity, ButtonEntity):
    """Asks Galaxy to do one thing."""

    entity_description: StarPilotButtonDescription

    def __init__(
        self,
        coordinator: StarPilotCoordinator,
        description: StarPilotButtonDescription,
        placeholders: dict[str, str] | None = None,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if placeholders is not None:
            self._attr_translation_placeholders = placeholders

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(self.coordinator.client)
        except GalaxyError as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="action_failed", translation_placeholders={"error": str(error)}
            ) from error
        self.coordinator.forget(*self.entity_description.refresh)
        await self.coordinator.async_refresh()
