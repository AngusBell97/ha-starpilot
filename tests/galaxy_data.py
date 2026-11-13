"""Sample Galaxy replies, shaped like a real comma four's (places and IDs are made up)."""

from __future__ import annotations

import copy
from typing import Any

HOTSPOT = {
    "version": 1,
    "config": {"enabled": False, "ssid": "TheGalaxy-ab12", "password": "hotspot-secret"},
    "active": False,
    "state": "disabled",
}

DRIVE_1 = {
    "routeId": "00000072--aaaaaaaaaa",
    "startTime": 1794592429.5,
    "endTime": 1794592619.1,
    "distanceMeters": 12414.93,
    "durationSeconds": 1189.566,
    "engagedSeconds": 900.0,
    "engagedPercent": 75.7,
    "model": "Light Speed 2 (Chestnut big)",
    "distractedMoments": 0,
    "unresponsiveMoments": 0,
    "complete": True,
    "reason": None,
    "ignored": False,
}
DRIVE_INCOMPLETE = {
    "routeId": "00000073--bbbbbbbbbb",
    "startTime": 1794593057.3,
    "endTime": 1794593205.5,
    "distanceMeters": None,
    "durationSeconds": 148.191,
    "engagedPercent": None,
    "model": "Light Speed 2 (Chestnut big)",
    "complete": False,
    "reason": "Route samples are missing or gapped",
    "ignored": False,
}
DRIVE_2 = {**DRIVE_1, "routeId": "00000074--cccccccccc", "distanceMeters": 40927.78, "endTime": 1794600000.0}

REPLIES: dict[str, Any] = {
    "/api/device/state": {"state": "parked", "maxAgeMs": 2666},
    "/api/drive-state/status": {
        "mode": "auto",
        "revision": "0123456789abcdef0123456789abcdef",
        "available": True,
        "effective": "offroad",
        "overrideAllowed": True,
        "reason": None,
    },
    "/api/system/monitor": {
        "schemaVersion": 1,
        "sampledAt": 1794603434.2,
        "deviceType": "mici",
        "cpuPercent": 13.4,
        "cores": [{"name": "cpu0", "percent": 20.9}, {"name": "cpu1", "percent": 13.6}],
        "processCount": 553,
        "memory": {"totalMiB": 3606.3, "usedMiB": 1210.5, "availableMiB": 2395.8, "percent": 33.6},
        "batteryVoltage": 13.46,
        "storage": {"usedGiB": 74.7, "totalGiB": 88.0, "freeGiB": 8.8},
        "uptimeSeconds": 5709.97,
        "processes": [{"pid": 1, "name": "init"}],
        "commaThermals": {
            "cpuTempC": 24.9,
            "gpuTempC": 22.9,
            "memoryTempC": 23.8,
            "maxTempC": 37.0,
            "fanPercent": 0,
            "status": "ok",
            "statusText": "Normal",
        },
        "externalGpus": [
            {
                "kind": "chestnut",
                "name": "Chestnut",
                "status": "idle",
                "statusText": "Connected · not running the driving model",
                "runningModel": False,
                "hotspotLimitC": 100.0,
                "memoryLimitC": 95.0,
                "hotspotC": None,
                "memoryTempC": None,
                "loadPercent": None,
                "clockMhz": None,
                "powerW": None,
                "powerLimitW": None,
                "fanRpm": None,
                "fanPercent": None,
                "frameMs": None,
                "supplyVolts": 13.32,
                "supplyAmps": 1.38,
                "usbSpeedMbps": 5000,
                "usbLinkErrors": 14,
                "peaksSince": 1793832632.8,
                "peaksResettable": True,
                "link": "GPU link up",
                "hotspotPeak": {"value": 53.0, "at": 1793902473.3},
                "memoryPeak": {"value": 72.0, "at": 1793888691.0},
            }
        ],
        "managed": {"expected": 20, "running": 20, "stopped": []},
    },
    "/api/navigation/status": {
        "enabled": True,
        "destination": None,
        "revision": "fedcba9876543210fedcba9876543210",
        "status": "noDestination",
        "instruction": None,
        "avoidTolls": False,
        "avoidHighways": False,
        "avoidFerries": False,
        "slowForTurns": True,
        "gpsSource": "comma",
        "network": "unknown",
        "mapboxUsage": {
            "searchSessions": {"used": 3, "limit": 495, "free": 500},
            "geocoding": {"used": 0, "limit": 99000, "free": 100000},
            "staticTiles": {"used": 25, "limit": 198000, "free": 200000},
            "directions": {"used": 15, "limit": 99000, "free": 100000},
        },
        "location": {"longitude": -1.5, "latitude": 52.5, "bearing": 73.6, "lastKnown": True},
    },
    "/api/drives/stats": {
        "schemaVersion": 1,
        "analysis": {"running": False, "pending": 0, "state": "idle", "failed": 0},
        "totals": {"distanceMeters": 242840.65, "durationSeconds": 22281.7, "engagedSeconds": 12202.7, "drives": 33},
        "pastWeek": {"distanceMeters": 48830.72, "durationSeconds": 5055.1, "engagedSeconds": 2829.7, "drives": 3},
        "records": [
            {"id": "longestDrive", "label": "Longest drive", "value": 53407.57, "unit": "m"},
            {"id": "mostEngagedDay", "label": "Most engaged day", "value": 84.7, "unit": "%"},
            {"id": "highestStreak", "label": "Highest streak", "value": 6, "unit": "days"},
            {"id": "cleanDriveStreak", "label": "Clean drive streak", "value": 33, "unit": "drives"},
        ],
        "lastDrive": DRIVE_INCOMPLETE,
        "recentDrives": [DRIVE_INCOMPLETE, DRIVE_1],
    },
    "/api/models/status": {
        "schemaVersion": 1,
        "catalog": [
            {"id": "lightspeed2", "name": "Light Speed 2", "selectable": True},
            {"id": "other", "name": "Other", "selectable": True},
        ],
        "requestedId": "lightspeed2",
        "loadedId": None,
        "health": "unavailable",
    },
    "/api/software/status?history=0": {
        "schemaVersion": 1,
        "installed": {
            "version": "0.11.3",
            "displayVersion": "7.0",
            "branch": "Dom",
            "commit": "0a1b2c3d4e5f60718293a4b5c6d7e8f901234567",
        },
        "updater": {
            "state": "idle",
            "targetBranch": "Dom",
            "lastCheckedAt": "2026-11-13T20:52:04.960333Z",
            "targetChangeFound": False,
            "finalizedUpdateReady": False,
        },
    },
    "/api/galaxy/hotspot": HOTSPOT,
    "/api/models/manager": {
        "models": [
            {"value": "lightspeed2", "label": "Light Speed 2", "installed": True},
            {"value": "polaris", "label": "Polaris", "installed": True},
        ],
        "activeSmallModel": "polaris",
        "activeBigModel": "lightspeed2",
        "summary": {"total": 111, "installed": 4, "missing": 107},
        "downloading": False,
    },
    "/api/weather": {"status": "ok", "temperatureC": 9.5},
    "/api/sentry/events": {"schemaVersion": 1, "events": [], "storageBytes": 0},
    "/api/crash-reports": {
        "reports": [{"id": "a", "name": "a.log", "size": 10, "modifiedAt": 1794410206.0}],
        "reportCount": 64,
        "storageBytes": 632078411,
    },
    "/api/settings/non-defaults": {"view": "v", "rows": [{"id": 0, "label": "x"}], "count": 87},
    "/api/galaxy/status": {"paired": True, "url": "https://example.invalid/secret-slug"},
    "/api/settings/pages/sounds": {
        "page": "sounds",
        "title": "Sounds & Alerts",
        "parked": True,
        "view": "view-1",
        "rows": [
            {"label": "Immediate Warning", "value": "Auto", "choices": ["25%", "50%", "Auto"], "available": True},
            {"label": "Engagement Chime", "value": "Auto", "choices": ["0%", "50%", "Auto"], "available": True, "unit": "%"},
            {"label": "Locked", "value": "Off", "choices": ["On", "Off"], "available": False, "reason": "Needs a car"},
        ],
    },
}


def replies() -> dict[str, Any]:
    """A fresh copy that a test can change."""
    return copy.deepcopy(REPLIES)
