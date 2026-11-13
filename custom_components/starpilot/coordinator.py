"""Polls Galaxy and shares one copy of the result with every entity."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GalaxyAccessError, GalaxyApiError, GalaxyClient, GalaxyConnectionError, GalaxyError
from .const import DEVICE_MODELS, DOMAIN, LOGGER, UPDATE_INTERVAL_SECONDS

type StarPilotConfigEntry = ConfigEntry[StarPilotCoordinator]

# Address and how often to read it, in seconds. The parked / driving state is read on every poll.
SECTIONS: dict[str, tuple[str, int]] = {
    "state": ("/api/device/state", 0),
    "drive_state": ("/api/drive-state/status", 0),
    "monitor": ("/api/system/monitor", 60),
    "navigation": ("/api/navigation/status", 60),
    "drives": ("/api/drives/stats", 120),
    "models": ("/api/models/status", 300),
    "software": ("/api/software/status?history=0", 300),
    "manager": ("/api/models/manager", 300),
    "weather": ("/api/weather", 300),
    "sentry": ("/api/sentry/events", 120),
    "crashes": ("/api/crash-reports", 600),
    "changed": ("/api/settings/non-defaults", 600),
    "remote": ("/api/galaxy/status", 300),
    "hotspot": ("/api/galaxy/hotspot", 300),
}
# Only the vehicle state is needed for the device to count as reachable; the rest may be missing on older builds.
REQUIRED = ("state",)
# Galaxy only works out CPU usage when its previous reading was under ten seconds earlier.
CPU_RESAMPLE_SECONDS = 2.0


def dig(data: Any, *path: str) -> Any:
    """Read a nested value, or None when any step is missing."""
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def latest_drive(data: dict[str, Any]) -> dict[str, Any] | None:
    """The most recent drive Galaxy finished analysing, else the most recent drive."""
    recent = dig(data, "drives", "recentDrives")
    if isinstance(recent, list):
        for drive in recent:
            if isinstance(drive, dict) and drive.get("complete") and not drive.get("ignored"):
                return drive
    last = dig(data, "drives", "lastDrive")
    return last if isinstance(last, dict) else None


def external_gpu(data: dict[str, Any]) -> dict[str, Any] | None:
    """The first external GPU Galaxy reports, such as a Chestnut."""
    gpus = dig(data, "monitor", "externalGpus")
    if isinstance(gpus, list) and gpus and isinstance(gpus[0], dict):
        return gpus[0]
    return None


def _names(rows: Any, key: str, label: str) -> dict[str, str]:
    if not isinstance(rows, list):
        return {}
    return {row[key]: row[label] for row in rows if isinstance(row, dict) and key in row and label in row}


def trim(section: str, value: dict[str, Any]) -> dict[str, Any]:
    """Keep what entities read. Drops bulky lists and anything private (remote link, hotspot password)."""
    if section == "monitor":
        # Several hundred process rows that no entity uses.
        value.pop("processes", None)
    elif section == "models":
        value["names"] = _names(value.pop("catalog", None), "id", "name")
    elif section == "manager":
        return {
            "activeSmallModel": value.get("activeSmallModel"),
            "activeBigModel": value.get("activeBigModel"),
            "names": _names(value.get("models"), "value", "label"),
            "installed": dig(value, "summary", "installed"),
            "downloading": value.get("downloading"),
        }
    elif section == "crashes":
        reports = value.get("reports")
        times = [row.get("modifiedAt") for row in reports if isinstance(row, dict)] if isinstance(reports, list) else []
        times = [stamp for stamp in times if isinstance(stamp, (int, float))]
        return {
            "reportCount": value.get("reportCount"),
            "storageBytes": value.get("storageBytes"),
            "latest": max(times) if times else None,
        }
    elif section == "changed":
        return {"count": value.get("count")}
    elif section == "sentry":
        events = value.get("events")
        return {"count": len(events) if isinstance(events, list) else None, "storageBytes": value.get("storageBytes")}
    elif section == "remote":
        return {"paired": value.get("paired")}
    elif section == "hotspot":
        return {"active": value.get("active"), "state": value.get("state"), "enabled": dig(value, "config", "enabled")}
    return value


class StarPilotCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One poller per comma."""

    config_entry: StarPilotConfigEntry

    def __init__(self, hass: HomeAssistant, entry: StarPilotConfigEntry, client: GalaxyClient) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client
        self._read_at: dict[str, float] = {}
        self._sections: dict[str, Any] = {}

    @property
    def device_info(self) -> DeviceInfo:
        """The comma as a Home Assistant device."""
        data = self.data or {}
        version = dig(data, "software", "installed", "displayVersion")
        branch = dig(data, "software", "installed", "branch")
        device_type = dig(data, "monitor", "deviceType")
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name=self.config_entry.title,
            manufacturer="comma.ai",
            model=DEVICE_MODELS.get(device_type, device_type) if isinstance(device_type, str) else None,
            sw_version=f"StarPilot {version} ({branch})" if version and branch else version,
            configuration_url=self.client.base_url,
        )

    def forget(self, *sections: str) -> None:
        """Read these sections again on the next poll, for use right after an action."""
        for section in sections:
            self._read_at.pop(section, None)

    async def _async_update_data(self) -> dict[str, Any]:
        now = time.monotonic()
        for section, (path, interval) in SECTIONS.items():
            read_at = self._read_at.get(section)
            if read_at is not None and interval and now - read_at < interval - 1:
                continue
            try:
                value = await self.client.async_get(path)
            except GalaxyConnectionError as error:
                raise UpdateFailed(f"The comma is not reachable: {error}") from error
            except GalaxyAccessError as error:
                raise UpdateFailed(f"Galaxy refused the request: {error}") from error
            except GalaxyApiError as error:
                # One part of Galaxy can be unavailable (503 while it starts up) without the rest failing.
                LOGGER.debug("Galaxy %s is unavailable: %s", path, error)
                if section in REQUIRED:
                    raise UpdateFailed(f"Galaxy has no vehicle state: {error}") from error
                continue
            if not isinstance(value, dict):
                continue
            if section == "monitor" and value.get("cpuPercent") is None:
                await asyncio.sleep(CPU_RESAMPLE_SECONDS)
                try:
                    again = await self.client.async_get(path)
                except GalaxyError:
                    again = None
                if isinstance(again, dict):
                    value = again
            value = trim(section, value)
            self._sections[section] = value
            self._read_at[section] = now
        return dict(self._sections)
