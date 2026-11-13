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
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfInformation,
    UnitOfLength,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import DEVICE_STATES, NAVIGATION_STATES
from .coordinator import StarPilotConfigEntry, StarPilotCoordinator, dig, external_gpu, latest_drive
from .entity import StarPilotEntity

PARALLEL_UPDATES = 0

DIAGNOSTIC = EntityCategory.DIAGNOSTIC
MEASUREMENT = SensorStateClass.MEASUREMENT
Data = dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class StarPilotSensorDescription(SensorEntityDescription):
    """A sensor and how to read it from the Galaxy poll."""

    value_fn: Callable[[Data], StateType | datetime]
    attributes_fn: Callable[[Data], dict[str, Any] | None] | None = None


def _number(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _kilometres(value: Any) -> float | None:
    metres = _number(value)
    return None if metres is None else round(metres / 1000, 2)


def _timestamp(value: Any) -> datetime | None:
    seconds = _number(value)
    if seconds is None or seconds <= 0:
        return None
    return datetime.fromtimestamp(int(seconds), UTC)


def _iso_time(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _option(value: Any, options: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    # Galaxy uses camelCase (noDestination); Home Assistant state keys are snake_case.
    key = re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()
    return key if key in options else None


def _share(part: Any, whole: Any) -> float | None:
    part, whole = _number(part), _number(whole)
    if part is None or not whole:
        return None
    return round(100 * part / whole, 1)


def _last_boot(data: Data) -> datetime | None:
    sampled, uptime = _number(dig(data, "monitor", "sampledAt")), _number(dig(data, "monitor", "uptimeSeconds"))
    if sampled is None or uptime is None:
        return None
    # Whole minutes, so reading jitter does not write a new state on every poll.
    return datetime.fromtimestamp(round((sampled - uptime) / 60) * 60, UTC)


def _model_name(data: Data, model_id: Any) -> str | None:
    if not isinstance(model_id, str) or not model_id:
        return None
    for section in ("models", "manager"):
        name = (dig(data, section, "names") or {}).get(model_id)
        if name:
            return name
    return model_id


def _drive(key: str) -> Callable[[Data], Any]:
    return lambda data: (latest_drive(data) or {}).get(key)


def _gpu(key: str) -> Callable[[Data], Any]:
    return lambda data: (external_gpu(data) or {}).get(key)


def _gpu_supply_power(data: Data) -> float | None:
    volts, amps = _number(_gpu("supplyVolts")(data)), _number(_gpu("supplyAmps")(data))
    return None if volts is None or amps is None else round(volts * amps, 1)


def _record(record_id: str) -> Callable[[Data], Any]:
    def read(data: Data) -> Any:
        records = dig(data, "drives", "records")
        for record in records if isinstance(records, list) else ():
            if isinstance(record, dict) and record.get("id") == record_id:
                return _number(record.get("value"))
        return None

    return read


def _instruction(data: Data) -> str | None:
    instruction = dig(data, "navigation", "instruction")
    if isinstance(instruction, dict):
        instruction = instruction.get("text") or instruction.get("instruction")
    return _text(instruction)


def _described(key: str, value_fn: Callable[[Data], Any], defaults: dict[str, Any], extra: dict[str, Any]) -> StarPilotSensorDescription:
    return StarPilotSensorDescription(key=key, translation_key=key, value_fn=value_fn, **{**defaults, **extra})


def _temperature(key: str, value_fn: Callable[[Data], Any], **extra: Any) -> StarPilotSensorDescription:
    defaults = {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
        "state_class": MEASUREMENT,
        "suggested_display_precision": 0,
    }
    return _described(key, lambda data: _number(value_fn(data)), defaults, extra)


def _percent(key: str, value_fn: Callable[[Data], Any], **extra: Any) -> StarPilotSensorDescription:
    defaults = {"native_unit_of_measurement": PERCENTAGE, "suggested_display_precision": 0}
    return _described(key, lambda data: _number(value_fn(data)), defaults, extra)


def _distance(key: str, value_fn: Callable[[Data], Any], **extra: Any) -> StarPilotSensorDescription:
    defaults = {
        "device_class": SensorDeviceClass.DISTANCE,
        "native_unit_of_measurement": UnitOfLength.KILOMETERS,
        "suggested_display_precision": 1,
    }
    return _described(key, lambda data: _kilometres(value_fn(data)), defaults, extra)


def _duration(key: str, value_fn: Callable[[Data], Any], unit: str = UnitOfTime.MINUTES, **extra: Any) -> StarPilotSensorDescription:
    defaults = {
        "device_class": SensorDeviceClass.DURATION,
        "native_unit_of_measurement": UnitOfTime.SECONDS,
        "suggested_unit_of_measurement": unit,
        "suggested_display_precision": 0 if unit == UnitOfTime.MINUTES else 1,
    }
    return _described(key, lambda data: _number(value_fn(data)), defaults, extra)


def _count(key: str, value_fn: Callable[[Data], Any], **extra: Any) -> StarPilotSensorDescription:
    return StarPilotSensorDescription(
        key=key, translation_key=key, value_fn=lambda data: _number(value_fn(data)), **extra
    )


def _plain(key: str, value_fn: Callable[[Data], Any], **extra: Any) -> StarPilotSensorDescription:
    return StarPilotSensorDescription(key=key, translation_key=key, value_fn=lambda data: _text(value_fn(data)), **extra)


SENSORS: tuple[StarPilotSensorDescription, ...] = (
    StarPilotSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=list(DEVICE_STATES),
        value_fn=lambda data: _option(dig(data, "state", "state"), DEVICE_STATES),
    ),
    StarPilotSensorDescription(
        key="drive_state_in_effect",
        translation_key="drive_state_in_effect",
        device_class=SensorDeviceClass.ENUM,
        options=["offroad", "onroad"],
        entity_category=DIAGNOSTIC,
        value_fn=lambda data: _option(dig(data, "drive_state", "effective"), ("offroad", "onroad")),
    ),
    # Device health
    _temperature(
        "temperature",
        lambda data: dig(data, "monitor", "commaThermals", "maxTempC"),
        attributes_fn=lambda data: {"status": dig(data, "monitor", "commaThermals", "statusText")},
    ),
    _temperature("cpu_temperature", lambda data: dig(data, "monitor", "commaThermals", "cpuTempC"), entity_category=DIAGNOSTIC),
    _temperature("gpu_temperature", lambda data: dig(data, "monitor", "commaThermals", "gpuTempC"), entity_category=DIAGNOSTIC),
    _temperature(
        "memory_temperature", lambda data: dig(data, "monitor", "commaThermals", "memoryTempC"), entity_category=DIAGNOSTIC
    ),
    _plain("thermal_status", lambda data: dig(data, "monitor", "commaThermals", "statusText"), entity_category=DIAGNOSTIC),
    _percent("fan_speed", lambda data: dig(data, "monitor", "commaThermals", "fanPercent"), state_class=MEASUREMENT, entity_category=DIAGNOSTIC),
    _percent("cpu_usage", lambda data: dig(data, "monitor", "cpuPercent"), state_class=MEASUREMENT),
    _percent("memory_usage", lambda data: dig(data, "monitor", "memory", "percent"), state_class=MEASUREMENT, entity_category=DIAGNOSTIC),
    StarPilotSensorDescription(
        key="memory_used",
        translation_key="memory_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number(dig(data, "monitor", "memory", "usedMiB")),
        attributes_fn=lambda data: {
            "total_mib": dig(data, "monitor", "memory", "totalMiB"),
            "available_mib": dig(data, "monitor", "memory", "availableMiB"),
        },
    ),
    StarPilotSensorDescription(
        key="storage_free",
        translation_key="storage_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda data: _number(dig(data, "monitor", "storage", "freeGiB")),
        attributes_fn=lambda data: {
            "used_gib": dig(data, "monitor", "storage", "usedGiB"),
            "total_gib": dig(data, "monitor", "storage", "totalGiB"),
        },
    ),
    _percent(
        "storage_usage",
        lambda data: _share(dig(data, "monitor", "storage", "usedGiB"), dig(data, "monitor", "storage", "totalGiB")),
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
    ),
    StarPilotSensorDescription(
        key="car_battery_voltage",
        translation_key="car_battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: _number(dig(data, "monitor", "batteryVoltage")),
    ),
    StarPilotSensorDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=DIAGNOSTIC,
        value_fn=_last_boot,
    ),
    _count(
        "processes",
        lambda data: dig(data, "monitor", "managed", "running"),
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
        attributes_fn=lambda data: {
            "expected": dig(data, "monitor", "managed", "expected"),
            "stopped": dig(data, "monitor", "managed", "stopped"),
        },
    ),
    _count("process_count", lambda data: dig(data, "monitor", "processCount"), state_class=MEASUREMENT, entity_category=DIAGNOSTIC),
    # Software
    _plain(
        "version",
        lambda data: dig(data, "software", "installed", "displayVersion"),
        entity_category=DIAGNOSTIC,
        attributes_fn=lambda data: {
            "openpilot_version": dig(data, "software", "installed", "version"),
            "branch": dig(data, "software", "installed", "branch"),
            "commit": (dig(data, "software", "installed", "commit") or "")[:10] or None,
        },
    ),
    _plain("branch", lambda data: dig(data, "software", "installed", "branch"), entity_category=DIAGNOSTIC),
    _plain("updater_state", lambda data: dig(data, "software", "updater", "state"), entity_category=DIAGNOSTIC),
    StarPilotSensorDescription(
        key="last_update_check",
        translation_key="last_update_check",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=DIAGNOSTIC,
        value_fn=lambda data: _iso_time(dig(data, "software", "updater", "lastCheckedAt")),
    ),
    _count("changed_settings", lambda data: dig(data, "changed", "count"), entity_category=DIAGNOSTIC),
    _count(
        "crash_reports",
        lambda data: dig(data, "crashes", "reportCount"),
        entity_category=DIAGNOSTIC,
        attributes_fn=lambda data: {
            "storage_bytes": dig(data, "crashes", "storageBytes"),
            "latest": _timestamp(dig(data, "crashes", "latest")),
        },
    ),
    _count("sentry_events", lambda data: dig(data, "sentry", "count")),
    _temperature("outside_temperature", lambda data: dig(data, "weather", "temperatureC"), entity_category=DIAGNOSTIC),
    # Driving models
    StarPilotSensorDescription(
        key="driving_model",
        translation_key="driving_model",
        value_fn=lambda data: _model_name(data, dig(data, "models", "requestedId")),
        attributes_fn=lambda data: {
            "model_id": dig(data, "models", "requestedId"),
            "health": dig(data, "models", "health"),
            "fallback_reason": dig(data, "models", "fallbackReason"),
            "pending_next_start": dig(data, "models", "pendingNextStart"),
        },
    ),
    StarPilotSensorDescription(
        key="loaded_model",
        translation_key="loaded_model",
        value_fn=lambda data: _model_name(data, dig(data, "models", "loadedId")),
        attributes_fn=lambda data: {"model_id": dig(data, "models", "loadedId"), "variant": dig(data, "models", "variant")},
    ),
    StarPilotSensorDescription(
        key="small_model",
        translation_key="small_model",
        value_fn=lambda data: _model_name(data, dig(data, "manager", "activeSmallModel")),
        attributes_fn=lambda data: {"model_id": dig(data, "manager", "activeSmallModel")},
    ),
    _plain("model_health", lambda data: dig(data, "models", "health"), entity_category=DIAGNOSTIC),
    _count("models_installed", lambda data: dig(data, "manager", "installed"), entity_category=DIAGNOSTIC),
    # Drives
    _distance("last_drive_distance", _drive("distanceMeters")),
    _duration("last_drive_duration", _drive("durationSeconds")),
    _percent("last_drive_engaged", _drive("engagedPercent")),
    _percent("last_drive_always_on_lateral", _drive("aolPercent")),
    StarPilotSensorDescription(
        key="last_drive_start",
        translation_key="last_drive_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: _timestamp(_drive("startTime")(data)),
    ),
    StarPilotSensorDescription(
        key="last_drive_end",
        translation_key="last_drive_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: _timestamp(_drive("endTime")(data)),
        attributes_fn=lambda data: {"route_id": _drive("routeId")(data)},
    ),
    _plain("last_drive_model", _drive("model")),
    _count("last_drive_distracted", _drive("distractedMoments")),
    _count("last_drive_unresponsive", _drive("unresponsiveMoments")),
    _distance("week_distance", lambda data: dig(data, "drives", "pastWeek", "distanceMeters"), suggested_display_precision=0),
    _duration("week_duration", lambda data: dig(data, "drives", "pastWeek", "durationSeconds"), UnitOfTime.HOURS),
    _count("week_drives", lambda data: dig(data, "drives", "pastWeek", "drives")),
    _percent(
        "week_engaged",
        lambda data: _share(dig(data, "drives", "pastWeek", "engagedSeconds"), dig(data, "drives", "pastWeek", "durationSeconds")),
    ),
    _distance("total_distance", lambda data: dig(data, "drives", "totals", "distanceMeters"), suggested_display_precision=0),
    _duration("total_duration", lambda data: dig(data, "drives", "totals", "durationSeconds"), UnitOfTime.HOURS),
    _count("total_drives", lambda data: dig(data, "drives", "totals", "drives")),
    _percent(
        "total_engaged",
        lambda data: _share(dig(data, "drives", "totals", "engagedSeconds"), dig(data, "drives", "totals", "durationSeconds")),
    ),
    _distance("record_longest_drive", _record("longestDrive"), entity_category=DIAGNOSTIC),
    _distance("record_best_week", _record("bestWeek"), entity_category=DIAGNOSTIC, suggested_display_precision=0),
    _percent("record_most_engaged_day", _record("mostEngagedDay"), entity_category=DIAGNOSTIC),
    _duration("record_longest_undistracted_drive", _record("longestUndistractedDrive"), entity_category=DIAGNOSTIC),
    StarPilotSensorDescription(
        key="record_highest_streak",
        translation_key="record_highest_streak",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        entity_category=DIAGNOSTIC,
        value_fn=_record("highestStreak"),
    ),
    _count("record_clean_drive_streak", _record("cleanDriveStreak"), entity_category=DIAGNOSTIC),
    _plain(
        "drive_analysis",
        lambda data: dig(data, "drives", "analysis", "state"),
        entity_category=DIAGNOSTIC,
        attributes_fn=lambda data: {
            "running": dig(data, "drives", "analysis", "running"),
            "pending": dig(data, "drives", "analysis", "pending"),
            "failed": dig(data, "drives", "analysis", "failed"),
        },
    ),
    # Navigation
    StarPilotSensorDescription(
        key="navigation",
        translation_key="navigation",
        device_class=SensorDeviceClass.ENUM,
        options=list(NAVIGATION_STATES),
        value_fn=lambda data: _option(dig(data, "navigation", "status"), NAVIGATION_STATES),
    ),
    StarPilotSensorDescription(
        key="destination",
        translation_key="destination",
        value_fn=lambda data: _text(dig(data, "navigation", "destination", "name")),
        attributes_fn=lambda data: {
            "address": dig(data, "navigation", "destination", "address"),
            "latitude": dig(data, "navigation", "destination", "latitude"),
            "longitude": dig(data, "navigation", "destination", "longitude"),
        },
    ),
    StarPilotSensorDescription(key="navigation_instruction", translation_key="navigation_instruction", value_fn=_instruction),
    _plain("gps_source", lambda data: dig(data, "navigation", "gpsSource"), entity_category=DIAGNOSTIC),
    StarPilotSensorDescription(
        key="navigation_network",
        translation_key="navigation_network",
        device_class=SensorDeviceClass.ENUM,
        options=["online", "offline", "unknown"],
        entity_category=DIAGNOSTIC,
        value_fn=lambda data: _option(dig(data, "navigation", "network"), ("online", "offline", "unknown")),
    ),
    *(
        _count(
            f"mapbox_{key}",
            lambda data, field=field: dig(data, "navigation", "mapboxUsage", field, "used"),
            entity_category=DIAGNOSTIC,
            attributes_fn=lambda data, field=field: {
                "limit": dig(data, "navigation", "mapboxUsage", field, "limit"),
                "free_allowance": dig(data, "navigation", "mapboxUsage", field, "free"),
            },
        )
        for key, field in (
            ("searches", "searchSessions"),
            ("geocoding", "geocoding"),
            ("map_tiles", "staticTiles"),
            ("directions", "directions"),
        )
    ),
)

# Created only when Galaxy reports an external GPU such as a Chestnut; {gpu} is its name.
GPU_SENSORS: tuple[StarPilotSensorDescription, ...] = (
    _plain(
        "external_gpu_status",
        _gpu("statusText"),
        attributes_fn=lambda data: {
            "state": _gpu("status")(data),
            "detail": _gpu("detail")(data),
            "note": _gpu("readingsNote")(data),
        },
    ),
    _plain("external_gpu_link", _gpu("link"), entity_category=DIAGNOSTIC),
    _temperature(
        "external_gpu_temperature", _gpu("hotspotC"), attributes_fn=lambda data: {"limit": _gpu("hotspotLimitC")(data)}
    ),
    _temperature(
        "external_gpu_memory_temperature",
        _gpu("memoryTempC"),
        attributes_fn=lambda data: {"limit": _gpu("memoryLimitC")(data)},
    ),
    StarPilotSensorDescription(
        key="external_gpu_highest_temperature",
        translation_key="external_gpu_highest_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number(dig(external_gpu(data), "hotspotPeak", "value")),
        attributes_fn=lambda data: {
            "logged_at": _timestamp(dig(external_gpu(data), "hotspotPeak", "at")),
            "since": _timestamp(_gpu("peaksSince")(data)),
        },
    ),
    StarPilotSensorDescription(
        key="external_gpu_highest_memory_temperature",
        translation_key="external_gpu_highest_memory_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number(dig(external_gpu(data), "memoryPeak", "value")),
        attributes_fn=lambda data: {
            "logged_at": _timestamp(dig(external_gpu(data), "memoryPeak", "at")),
            "since": _timestamp(_gpu("peaksSince")(data)),
        },
    ),
    _percent("external_gpu_usage", _gpu("loadPercent"), state_class=MEASUREMENT),
    StarPilotSensorDescription(
        key="external_gpu_power",
        translation_key="external_gpu_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data: _number(_gpu("powerW")(data)),
        attributes_fn=lambda data: {"limit": _gpu("powerLimitW")(data)},
    ),
    StarPilotSensorDescription(
        key="external_gpu_supply_power",
        translation_key="external_gpu_supply_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_gpu_supply_power,
    ),
    StarPilotSensorDescription(
        key="external_gpu_supply_voltage",
        translation_key="external_gpu_supply_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda data: _number(_gpu("supplyVolts")(data)),
    ),
    StarPilotSensorDescription(
        key="external_gpu_supply_current",
        translation_key="external_gpu_supply_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda data: _number(_gpu("supplyAmps")(data)),
    ),
    StarPilotSensorDescription(
        key="external_gpu_clock",
        translation_key="external_gpu_clock",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number(_gpu("clockMhz")(data)),
    ),
    StarPilotSensorDescription(
        key="external_gpu_fan_speed",
        translation_key="external_gpu_fan_speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number(_gpu("fanRpm")(data)),
        attributes_fn=lambda data: {"percent": _gpu("fanPercent")(data)},
    ),
    StarPilotSensorDescription(
        key="external_gpu_frame_time",
        translation_key="external_gpu_frame_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=MEASUREMENT,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda data: _number(_gpu("frameMs")(data)),
    ),
    StarPilotSensorDescription(
        key="external_gpu_usb_speed",
        translation_key="external_gpu_usb_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        entity_category=DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda data: _number(_gpu("usbSpeedMbps")(data)),
    ),
    _count(
        "external_gpu_usb_link_errors",
        _gpu("usbLinkErrors"),
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=DIAGNOSTIC,
    ),
)


def _core_sensors(data: Data) -> list[tuple[StarPilotSensorDescription, dict[str, str]]]:
    """One usage sensor per CPU core Galaxy lists; off until asked for."""
    cores = dig(data, "monitor", "cores")
    result = []
    for index in range(len(cores) if isinstance(cores, list) else 0):

        def read(data: Data, index: int = index) -> Any:
            rows = dig(data, "monitor", "cores")
            return rows[index].get("percent") if isinstance(rows, list) and index < len(rows) and isinstance(rows[index], dict) else None

        result.append(
            (
                _percent(
                    f"cpu_core_{index}_usage",
                    read,
                    state_class=MEASUREMENT,
                    entity_category=DIAGNOSTIC,
                    entity_registry_enabled_default=False,
                ),
                {"core": str(index)},
            )
        )
    return result


async def async_setup_entry(
    hass: HomeAssistant, entry: StarPilotConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(StarPilotSensor(coordinator, description) for description in SENSORS)
    async_add_entities(
        StarPilotSensor(coordinator, description, placeholders, "cpu_core_usage")
        for description, placeholders in _core_sensors(coordinator.data)
    )

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
        translation_key: str | None = None,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if placeholders is not None:
            self._attr_translation_placeholders = placeholders
        if translation_key is not None:
            self._attr_translation_key = translation_key

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        attributes = self.entity_description.attributes_fn(self.coordinator.data) or {}
        return {key: value for key, value in attributes.items() if value is not None}
