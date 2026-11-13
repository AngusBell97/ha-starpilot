"""What Home Assistant shows for a comma."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.starpilot.api import GalaxyApiError, GalaxyConnectionError
from custom_components.starpilot.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import FakeGalaxy
from .galaxy_data import DRIVE_2


async def _poll(hass: HomeAssistant, seconds: int = 31) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id is not None, f"{platform} {key} was not created"
    return hass.states.get(entity_id)


async def test_values(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert loaded.state is ConfigEntryState.LOADED
    assert _state(hass, loaded, "sensor", "status").state == "parked"
    assert _state(hass, loaded, "binary_sensor", "driving").state == STATE_OFF
    assert _state(hass, loaded, "sensor", "temperature").state == "37.0"
    assert _state(hass, loaded, "sensor", "car_battery_voltage").state == "13.46"
    assert _state(hass, loaded, "sensor", "storage_free").state == "8.8"
    assert _state(hass, loaded, "sensor", "version").state == "7.0"
    assert _state(hass, loaded, "sensor", "version").attributes["commit"] == "0a1b2c3d4e"
    assert _state(hass, loaded, "sensor", "driving_model").state == "Light Speed 2"
    assert _state(hass, loaded, "sensor", "navigation").state == "no_destination"
    assert _state(hass, loaded, "sensor", "destination").state == STATE_UNKNOWN
    assert _state(hass, loaded, "select", "drive_mode").state == "auto"
    assert _state(hass, loaded, "binary_sensor", "update_available").state == STATE_OFF
    assert _state(hass, loaded, "binary_sensor", "process_problem").state == STATE_OFF


async def test_last_drive_is_the_latest_complete_one(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    # The newest drive has no distance yet, so the last analysed one is shown.
    assert _state(hass, loaded, "sensor", "last_drive_distance").state == "12.41"
    assert _state(hass, loaded, "sensor", "last_drive_engaged").state == "75.7"
    assert _state(hass, loaded, "sensor", "last_drive_end").attributes["route_id"] == "00000072--aaaaaaaaaa"
    assert _state(hass, loaded, "sensor", "week_distance").state == "48.83"


async def test_external_gpu(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    status = _state(hass, loaded, "sensor", "external_gpu_status")
    assert status.state == "Connected · not running the driving model"
    assert status.attributes["friendly_name"] == "comma four Chestnut status"
    assert _state(hass, loaded, "sensor", "external_gpu_temperature").state == STATE_UNKNOWN
    assert _state(hass, loaded, "sensor", "external_gpu_temperature").attributes["limit"] == 100.0
    assert _state(hass, loaded, "binary_sensor", "external_gpu_running_model").state == STATE_OFF


async def test_no_external_gpu(hass: HomeAssistant, entry: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    galaxy.replies["/api/system/monitor"]["externalGpus"] = []
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_external_gpu_status") is None
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_temperature") is not None


async def test_device(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, loaded.entry_id), loaded.entry_id)
    assert device is not None
    assert device.manufacturer == "comma.ai" and device.model == "comma four"
    assert device.sw_version == "StarPilot 7.0 (Dom)"
    assert device.configuration_url == "http://192.168.1.50:8082"


async def test_process_rows_are_dropped(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert "processes" not in loaded.runtime_data.data["monitor"]
    assert "catalog" not in loaded.runtime_data.data["models"]


async def test_unreachable_then_back(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    galaxy.error = GalaxyConnectionError("timed out")
    await _poll(hass)
    assert _state(hass, loaded, "sensor", "status").state == STATE_UNAVAILABLE
    # The notification event does not depend on polling.
    assert _state(hass, loaded, "event", "notification").state != STATE_UNAVAILABLE

    galaxy.error = None
    galaxy.replies["/api/device/state"]["state"] = "driving"
    await _poll(hass)
    assert _state(hass, loaded, "sensor", "status").state == "driving"


async def test_one_failing_part_keeps_the_rest(hass: HomeAssistant, entry: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    del galaxy.replies["/api/navigation/status"]
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, entry, "sensor", "status").state == "parked"
    assert _state(hass, entry, "sensor", "navigation").state == STATE_UNKNOWN


async def test_not_ready_when_unreachable(hass: HomeAssistant, entry: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    galaxy.error = GalaxyConnectionError("no route to host")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_drive_mode(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    entity_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{loaded.entry_id}_drive_mode")
    await hass.services.async_call("select", "select_option", {"entity_id": entity_id, "option": "offroad"}, blocking=True)
    await hass.async_block_till_done()
    assert galaxy.posts == [("/api/drive-state/action", {"mode": "offroad", "revision": "0123456789abcdef0123456789abcdef"})]
    assert hass.states.get(entity_id).state == "offroad"


async def test_drive_mode_rejected(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    entity_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{loaded.entry_id}_drive_mode")
    galaxy.error = GalaxyApiError(409, "Park the vehicle and disengage before forcing Offroad")
    with pytest.raises(HomeAssistantError, match="Park the vehicle"):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": entity_id, "option": "offroad"}, blocking=True
        )


async def test_buttons(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    registry = er.async_get(hass)
    for key, expected in (
        ("check_for_updates", ("/api/software/action", {"action": "check"})),
        ("clear_destination", ("/api/navigation/action", {"action": "clear", "revision": "fedcba9876543210fedcba9876543210"})),
    ):
        entity_id = registry.async_get_entity_id("button", DOMAIN, f"{loaded.entry_id}_{key}")
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
        assert galaxy.posts[-1] == expected


async def test_drive_finished_event(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    assert _state(hass, loaded, "event", "drive").state == STATE_UNKNOWN
    # Nothing new: no event.
    await _poll(hass, 130)
    assert _state(hass, loaded, "event", "drive").state == STATE_UNKNOWN

    stats = galaxy.replies["/api/drives/stats"]
    stats["lastDrive"] = DRIVE_2
    stats["recentDrives"] = [DRIVE_2, *stats["recentDrives"]]
    await _poll(hass, 130)
    state = _state(hass, loaded, "event", "drive")
    assert state.attributes["event_type"] == "finished"
    assert state.attributes["route_id"] == "00000074--cccccccccc"
    assert state.attributes["distance_km"] == 40.93
    fired_at = state.state

    # The same drive again: no second event.
    await _poll(hass, 130)
    assert _state(hass, loaded, "event", "drive").state == fired_at


async def test_notification_event(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    hass.bus.async_fire(
        "starpilot_notification",
        {"title": "Sentry Mode", "message": "Movement near the car", "eventId": "e1", "kind": "alarm", "type": "sentry.alarm"},
    )
    await hass.async_block_till_done()
    state = _state(hass, loaded, "event", "notification")
    assert state.attributes["event_type"] == "sentry_alarm"
    assert state.attributes["message"] == "Movement near the car"

    # An unknown type is ignored instead of raising.
    hass.bus.async_fire("starpilot_notification", {"type": "something.else"})
    await hass.async_block_till_done()
    assert _state(hass, loaded, "event", "notification").attributes["event_type"] == "sentry_alarm"


async def test_tracker_is_off_by_default(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("device_tracker", DOMAIN, f"{loaded.entry_id}_location")
    assert entity_id is not None
    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_unload(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(loaded.entry_id)
    await hass.async_block_till_done()
    assert loaded.state is ConfigEntryState.NOT_LOADED


async def test_new_readings(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    for key, expected in (
        ("cpu_usage", "13.4"),
        ("memory_used", "1210.5"),
        ("storage_usage", "84.9"),
        ("process_count", "553"),
        ("thermal_status", "Normal"),
        ("drive_state_in_effect", "offroad"),
        ("branch", "Dom"),
        ("updater_state", "idle"),
        ("last_update_check", "2026-11-13T20:52:04+00:00"),
        ("changed_settings", "87"),
        ("crash_reports", "64"),
        ("sentry_events", "0"),
        ("outside_temperature", "9.5"),
        ("small_model", "Polaris"),
        ("loaded_model", STATE_UNKNOWN),
        ("model_health", "unavailable"),
        ("models_installed", "4"),
        ("last_drive_model", "Light Speed 2 (Chestnut big)"),
        ("last_drive_distracted", "0"),
        ("week_drives", "3"),
        ("week_engaged", "56.0"),
        ("total_drives", "33"),
        ("total_engaged", "54.8"),
        ("record_longest_drive", "53.41"),
        ("record_most_engaged_day", "84.7"),
        ("record_highest_streak", "6"),
        ("record_clean_drive_streak", "33"),
        ("record_best_week", STATE_UNKNOWN),
        ("drive_analysis", "idle"),
        ("gps_source", "comma"),
        ("navigation_network", "unknown"),
        ("mapbox_searches", "3"),
        ("mapbox_directions", "15"),
        ("external_gpu_supply_power", "18.4"),
        ("external_gpu_supply_current", "1.38"),
        ("external_gpu_usage", STATE_UNKNOWN),
        ("external_gpu_highest_temperature", "53.0"),
        ("external_gpu_highest_memory_temperature", "72.0"),
        ("external_gpu_usb_speed", "5000"),
        ("external_gpu_usb_link_errors", "14"),
        ("external_gpu_link", "GPU link up"),
    ):
        assert _state(hass, loaded, "sensor", key).state == expected, key
    assert _state(hass, loaded, "binary_sensor", "remote_access").state == "on"
    assert _state(hass, loaded, "binary_sensor", "hotspot").state == STATE_OFF
    assert _state(hass, loaded, "binary_sensor", "model_download").state == STATE_OFF


async def test_cpu_cores_are_off_by_default(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    registry = er.async_get(hass)
    for index in (0, 1):
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{loaded.entry_id}_cpu_core_{index}_usage")
        assert entity_id == f"sensor.comma_four_cpu_core_{index}_usage"
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_secrets_are_not_kept(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    text = repr(loaded.runtime_data.data)
    assert "secret-slug" not in text and "hotspot-secret" not in text


async def test_navigation_switches(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    assert _state(hass, loaded, "switch", "slow_for_turns").state == "on"
    assert _state(hass, loaded, "switch", "navigation_enabled").state == "on"
    entity_id = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{loaded.entry_id}_avoid_tolls")
    assert hass.states.get(entity_id).state == STATE_OFF
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()
    assert galaxy.posts[-1] == (
        "/api/navigation/action",
        {"action": "configure", "revision": "fedcba9876543210fedcba9876543210", "patch": {"avoidTolls": True}},
    )
    assert hass.states.get(entity_id).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF


async def test_reset_gpu_peaks_button(hass: HomeAssistant, loaded: MockConfigEntry, galaxy: FakeGalaxy) -> None:
    entity_id = er.async_get(hass).async_get_entity_id("button", DOMAIN, f"{loaded.entry_id}_reset_external_gpu_peaks")
    assert entity_id == "button.comma_four_reset_chestnut_highest_temperatures"
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    assert galaxy.posts[-1] == ("/api/system/monitor/reset-peaks", {"gpu": "chestnut"})
