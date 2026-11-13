"""Events for StarPilot: a finished drive, and notifications the comma sends."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import EVENT_NOTIFICATION, NOTIFICATION_TYPES
from .coordinator import StarPilotConfigEntry, StarPilotCoordinator, latest_drive
from .entity import StarPilotEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: StarPilotConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the event entities."""
    coordinator = entry.runtime_data
    async_add_entities([DriveEvent(coordinator), NotificationEvent(coordinator)])


class DriveEvent(StarPilotEntity, EventEntity):
    """Fires once when Galaxy has finished analysing a new drive."""

    _attr_translation_key = "drive"
    _attr_event_types = ["finished"]

    def __init__(self, coordinator: StarPilotCoordinator) -> None:
        super().__init__(coordinator, "drive")
        self._route_id = self._current_route()

    def _current_route(self) -> str | None:
        drive = latest_drive(self.coordinator.data)
        if drive is None or not drive.get("complete"):
            return None
        route_id = drive.get("routeId")
        return route_id if isinstance(route_id, str) else None

    @callback
    def _handle_coordinator_update(self) -> None:
        route_id = self._current_route()
        if route_id is not None and route_id != self._route_id:
            # The first drive seen after setup only sets the baseline; it may be days old.
            if self._route_id is not None:
                drive = latest_drive(self.coordinator.data) or {}
                distance = drive.get("distanceMeters")
                self._trigger_event(
                    "finished",
                    {
                        "route_id": route_id,
                        "distance_km": round(distance / 1000, 2) if isinstance(distance, (int, float)) else None,
                        "duration_seconds": drive.get("durationSeconds"),
                        "engaged_percent": drive.get("engagedPercent"),
                        "model": drive.get("model"),
                        "start_time": drive.get("startTime"),
                        "end_time": drive.get("endTime"),
                    },
                )
            self._route_id = route_id
        super()._handle_coordinator_update()


class NotificationEvent(StarPilotEntity, EventEntity):
    """Shows notifications the comma posts to Home Assistant.

    Needs the Home Assistant channel set up on Galaxy's Notifications page, pointing at
    /api/events/starpilot_notification. It works even while the comma is not being polled.
    """

    _attr_translation_key = "notification"
    _attr_event_types = list(NOTIFICATION_TYPES)

    def __init__(self, coordinator: StarPilotCoordinator) -> None:
        super().__init__(coordinator, "notification")

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.hass.bus.async_listen(EVENT_NOTIFICATION, self._handle_notification))

    @callback
    def _handle_notification(self, event: Event) -> None:
        data: dict[str, Any] = dict(event.data)
        kind = data.get("type")
        event_type = kind.replace(".", "_") if isinstance(kind, str) else None
        if event_type not in NOTIFICATION_TYPES:
            return
        attributes = {
            "title": data.get("title"),
            "message": data.get("message"),
            "event_id": data.get("eventId"),
            "time_ms": data.get("systemTimeMs"),
        }
        self._trigger_event(event_type, {key: value for key, value in attributes.items() if value is not None})
        self.async_write_ha_state()
