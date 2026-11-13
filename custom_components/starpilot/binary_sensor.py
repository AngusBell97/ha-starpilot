"""Binary sensors for StarPilot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import StarPilotConfigEntry, StarPilotCoordinator, dig, external_gpu
from .entity import StarPilotEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class StarPilotBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor and how to read it from the Galaxy poll."""

    is_on_fn: Callable[[dict[str, Any]], bool | None]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _driving(data: dict[str, Any]) -> bool | None:
    state = dig(data, "state", "state")
    return None if state is None else state == "driving"


def _update_available(data: dict[str, Any]) -> bool | None:
    updater = dig(data, "software", "updater")
    if not isinstance(updater, dict):
        return None
    return bool(updater.get("targetChangeFound") or updater.get("finalizedUpdateReady"))


def _process_problem(data: dict[str, Any]) -> bool | None:
    running, expected = dig(data, "monitor", "managed", "running"), dig(data, "monitor", "managed", "expected")
    if not isinstance(running, int) or not isinstance(expected, int):
        return None
    return running < expected


def _gpu_running_model(data: dict[str, Any]) -> bool | None:
    gpu = external_gpu(data)
    if gpu is None or not isinstance(gpu.get("runningModel"), bool):
        return None
    return gpu["runningModel"]


BINARY_SENSORS: tuple[StarPilotBinarySensorDescription, ...] = (
    StarPilotBinarySensorDescription(
        key="driving",
        translation_key="driving",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=_driving,
    ),
    StarPilotBinarySensorDescription(
        key="update_available",
        translation_key="update_available",
        device_class=BinarySensorDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=_update_available,
        attributes_fn=lambda data: {
            "target_branch": dig(data, "software", "updater", "targetBranch"),
            "last_checked": dig(data, "software", "updater", "lastCheckedAt"),
        },
    ),
    StarPilotBinarySensorDescription(
        key="process_problem",
        translation_key="process_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=_process_problem,
        attributes_fn=lambda data: {"stopped": dig(data, "monitor", "managed", "stopped")},
    ),
    StarPilotBinarySensorDescription(
        key="remote_access",
        translation_key="remote_access",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: _flag(dig(data, "remote", "paired")),
    ),
    StarPilotBinarySensorDescription(
        key="hotspot",
        translation_key="hotspot",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: _flag(dig(data, "hotspot", "active")),
    ),
    StarPilotBinarySensorDescription(
        key="model_download",
        translation_key="model_download",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: _flag(dig(data, "manager", "downloading")),
    ),
    StarPilotBinarySensorDescription(
        key="external_gpu_running_model",
        translation_key="external_gpu_running_model",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=_gpu_running_model,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: StarPilotConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        StarPilotBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.key != "external_gpu_running_model" or external_gpu(coordinator.data) is not None
    )


class StarPilotBinarySensor(StarPilotEntity, BinarySensorEntity):
    """One on/off value from the Galaxy poll."""

    entity_description: StarPilotBinarySensorDescription

    def __init__(self, coordinator: StarPilotCoordinator, description: StarPilotBinarySensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.key == "external_gpu_running_model":
            gpu = external_gpu(coordinator.data) or {}
            name = gpu.get("name")
            self._attr_translation_placeholders = {"gpu": name if isinstance(name, str) and name else "External GPU"}

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        attributes = self.entity_description.attributes_fn(self.coordinator.data) or {}
        return {key: value for key, value in attributes.items() if value is not None}
