"""Sensors for StarPilot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfInformation,
    UnitOfLength,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DEVICE_STATES, NAVIGATION_STATES
from .coordinator import StarPilotConfigEntry, StarPilotCoordinator, dig, external_gpu, latest_drive
from .entity import StarPilotEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class StarPilotSensorDescription(SensorEntityDescription):
    """A sensor and how to read it from the Galaxy poll."""

    value_fn: Callable[[dict[str, Any]], StateType | datetime]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None


def _number(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _kilometres(value: Any) -> float | None:
    metres = _number(value)
    return None if metres is None else round(metres / 1000, 2)


def _timestamp(value: Any) -> datetime | None:
    seconds = _number(value)
    if seconds is None or seconds <= 0:
        return None
    return datetime.fromtimestamp(int(seconds), UTC)


def _option(value: Any, options: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    # Galaxy uses camelCase (noDestination); Home Assistant state keys are snake_case.
    key = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    return key if key in options else None


def _last_boot(data: dict[str, Any]) -> datetime | None:
    sampled, uptime = _number(dig(data, "monitor", "sampledAt")), _number(dig(data, "monitor", "uptimeSeconds"))
    if sampled is None or uptime is None:
        return None
    # Whole minutes, so reading jitter does not write a new state on every poll.
    return datetime.fromtimestamp(round((sampled - uptime) / 60) * 60, UTC)


def _model_name(data: dict[str, Any]) -> str | None:
    requested = dig(data, "models", "requestedId")
    if not isinstance(requested, str):
        return None
    return (dig(data, "models", "names") or {}).get(requested, requested)


def _drive(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: (latest_drive(data) or {}).get(key)


SENSORS: tuple[StarPilotSensorDescription, ...] = (
    StarPilotSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=list(DEVICE_STATES),
        value_fn=lambda data: _option(dig(data, "state", "state"), DEVICE_STATES),
    ),
    # Device health
    StarPilotSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: _number(dig(data, "monitor", "commaThermals", "maxTempC")),
        attributes_fn=lambda data: {"status": dig(data, "monitor", "commaThermals", "statusText")},
    ),
    StarPilotSensorDescription(
        key="cpu_temperature",
        translation_key="cpu_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
        value_fn=lambda data: _number(dig(data, "monitor", "commaThermals", "cpuTempC")),
    ),
    StarPilotSensorDescription(
        key="gpu_temperature",
        translation_key="gpu_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
        value_fn=lambda data: _number(dig(data, "monitor", "commaThermals", "gpuTempC")),
    ),
    StarPilotSensorDescription(
        key="memory_temperature",
        translation_key="memory_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=0,
        value_fn=lambda data: _number(dig(data, "monitor", "commaThermals", "memoryTempC")),
    ),
    StarPilotSensorDescription(
        key="fan_speed",
        translation_key="fan_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _number(dig(data, "monitor", "commaThermals", "fanPercent")),
    ),
    StarPilotSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number(dig(data, "monitor", "memory", "percent")),
    ),
    StarPilotSensorDescription(
        key="storage_free",
        translation_key="storage_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda data: _number(dig(data, "monitor", "storage", "freeGiB")),
        attributes_fn=lambda data: {
            "used_gib": dig(data, "monitor", "storage", "usedGiB"),
            "total_gib": dig(data, "monitor", "storage", "totalGiB"),
        },
    ),
    StarPilotSensorDescription(
        key="car_battery_voltage",
        translation_key="car_battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: _number(dig(data, "monitor", "batteryVoltage")),
    ),
    StarPilotSensorDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_last_boot,
    ),
    StarPilotSensorDescription(
        key="processes",
        translation_key="processes",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: _number(dig(data, "monitor", "managed", "running")),
        attributes_fn=lambda data: {
            "expected": dig(data, "monitor", "managed", "expected"),
            "stopped": dig(data, "monitor", "managed", "stopped"),
        },
    ),
    # Software
    StarPilotSensorDescription(
        key="version",
        translation_key="version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: dig(data, "software", "installed", "displayVersion"),
        attributes_fn=lambda data: {
            "openpilot_version": dig(data, "software", "installed", "version"),
            "branch": dig(data, "software", "installed", "branch"),
            "commit": (dig(data, "software", "installed", "commit") or "")[:10] or None,
        },
    ),
    StarPilotSensorDescription(
        key="driving_model",
        translation_key="driving_model",
        value_fn=_model_name,
        attributes_fn=lambda data: {
            "model_id": dig(data, "models", "requestedId"),
            "loaded_model_id": dig(data, "models", "loadedId"),
            "health": dig(data, "models", "health"),
        },
    ),
    # Drives
    StarPilotSensorDescription(
        key="last_drive_distance",
        translation_key="last_drive_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=lambda data: _kilometres(_drive("distanceMeters")(data)),
    ),
    StarPilotSensorDescription(
        key="last_drive_duration",
        translation_key="last_drive_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda data: _number(_drive("durationSeconds")(data)),
    ),
    StarPilotSensorDescription(
        key="last_drive_engaged",
        translation_key="last_drive_engaged",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda data: _number(_drive("engagedPercent")(data)),
    ),
    StarPilotSensorDescription(
        key="last_drive_end",
        translation_key="last_drive_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: _timestamp(_drive("endTime")(data)),
        attributes_fn=lambda data: {
            "route_id": _drive("routeId")(data),
            "model": _drive("model")(data),
            "distracted_moments": _drive("distractedMoments")(data),
            "unresponsive_moments": _drive("unresponsiveMoments")(data),
        },
    ),
    StarPilotSensorDescription(
        key="week_distance",
        translation_key="week_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=0,
        value_fn=lambda data: _kilometres(dig(data, "drives", "pastWeek", "distanceMeters")),
        attributes_fn=lambda data: {"drives": dig(data, "drives", "pastWeek", "drives")},
    ),
    StarPilotSensorDescription(
        key="total_distance",
        translation_key="total_distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda data: _kilometres(dig(data, "drives", "totals", "distanceMeters")),
        attributes_fn=lambda data: {"drives": dig(data, "drives", "totals", "drives")},
    ),
    # Navigation
    StarPilotSensorDescription(
        key="navigation",
        translation_key="navigation",
        device_class=SensorDeviceClass.ENUM,
        options=list(NAVIGATION_STATES),
        value_fn=lambda data: _option(dig(data, "navigation", "status"), NAVIGATION_STATES),
        attributes_fn=lambda data: {"instruction": dig(data, "navigation", "instruction")},
    ),
    StarPilotSensorDescription(
        key="destination",
        translation_key="destination",
        value_fn=lambda data: dig(data, "navigation", "destination", "name"),
        attributes_fn=lambda data: {
            "address": dig(data, "navigation", "destination", "address"),
            "latitude": dig(data, "navigation", "destination", "latitude"),
            "longitude": dig(data, "navigation", "destination", "longitude"),
        },
    ),
)

# Created only when Galaxy reports an external GPU such as a Chestnut; {gpu} is its name.
GPU_SENSORS: tuple[StarPilotSensorDescription, ...] = (
    StarPilotSensorDescription(
        key="external_gpu_status",
        translation_key="external_gpu_status",
        value_fn=lambda data: (external_gpu(data) or {}).get("statusText"),
        attributes_fn=lambda data: {
            "state": (external_gpu(data) or {}).get("status"),
            "link": (external_gpu(data) or {}).get("link"),
            "running_model": (external_gpu(data) or {}).get("runningModel"),
        },
    ),
    StarPilotSensorDescription(
        key="external_gpu_temperature",
        translation_key="external_gpu_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: _number((external_gpu(data) or {}).get("hotspotC")),
        attributes_fn=lambda data: {
            "limit": (external_gpu(data) or {}).get("hotspotLimitC"),
            "highest_logged": dig(external_gpu(data), "hotspotPeak", "value"),
        },
    ),
    StarPilotSensorDescription(
        key="external_gpu_memory_temperature",
        translation_key="external_gpu_memory_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number((external_gpu(data) or {}).get("memoryTempC")),
        attributes_fn=lambda data: {
            "limit": (external_gpu(data) or {}).get("memoryLimitC"),
            "highest_logged": dig(external_gpu(data), "memoryPeak", "value"),
        },
    ),
    StarPilotSensorDescription(
        key="external_gpu_power",
        translation_key="external_gpu_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number((external_gpu(data) or {}).get("powerW")),
    ),
    StarPilotSensorDescription(
        key="external_gpu_supply_voltage",
        translation_key="external_gpu_supply_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=lambda data: _number((external_gpu(data) or {}).get("supplyVolts")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: StarPilotConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(StarPilotSensor(coordinator, description) for description in SENSORS)

    gpu_added = False

    @callback
    def add_gpu_sensors() -> None:
        # The GPU can be plugged in after Home Assistant starts.
        nonlocal gpu_added
        gpu = external_gpu(coordinator.data)
        if gpu_added or gpu is None:
            return
        gpu_added = True
        name = gpu.get("name") if isinstance(gpu.get("name"), str) and gpu.get("name") else "External GPU"
        async_add_entities(StarPilotSensor(coordinator, description, {"gpu": name}) for description in GPU_SENSORS)

    add_gpu_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_gpu_sensors))


class StarPilotSensor(StarPilotEntity, SensorEntity):
    """One value from the Galaxy poll."""

    entity_description: StarPilotSensorDescription

    def __init__(
        self,
        coordinator: StarPilotCoordinator,
        description: StarPilotSensorDescription,
        placeholders: dict[str, str] | None = None,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if placeholders is not None:
            self._attr_translation_placeholders = placeholders

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        attributes = self.entity_description.attributes_fn(self.coordinator.data) or {}
        return {key: value for key, value in attributes.items() if value is not None}
