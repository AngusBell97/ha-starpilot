"""Constants for the StarPilot integration."""

from __future__ import annotations

import logging

DOMAIN = "starpilot"
LOGGER = logging.getLogger(__package__)

DEFAULT_PORT = 8082
UPDATE_INTERVAL_SECONDS = 30

# Bus event the comma posts when its Home Assistant notification channel is set up in Galaxy.
EVENT_NOTIFICATION = "starpilot_notification"

DEVICE_MODELS = {"mici": "comma four", "tizi": "comma 3X", "tici": "comma three"}

DRIVE_MODES = ("auto", "offroad", "onroad")
DEVICE_STATES = ("parked", "standby", "driving")
NAVIGATION_STATES = (
    "disabled",
    "needs_key",
    "no_destination",
    "waiting_for_location",
    "routing",
    "route_unavailable",
    "guiding",
    "arrived",
)
NOTIFICATION_TYPES = (
    "sentry_warning",
    "sentry_alarm",
    "sentry_battery",
    "drive_summary",
    "model_release",
    "update_available",
    "update_installed",
    "test",
)
