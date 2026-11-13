"""Sample Galaxy replies, shaped like a real comma four's (places and IDs are made up)."""

from __future__ import annotations

import copy
from typing import Any

HOTSPOT = {"version": 1, "config": {"enabled": False, "ssid": "TheGalaxy-ab12", "password": ""}, "state": "disabled"}

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
                "powerW": None,
                "supplyVolts": 13.32,
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
        "location": {"longitude": -1.5, "latitude": 52.5, "bearing": 73.6, "lastKnown": True},
    },
    "/api/drives/stats": {
        "schemaVersion": 1,
        "totals": {"distanceMeters": 242840.65, "durationSeconds": 22281.7, "drives": 33},
        "pastWeek": {"distanceMeters": 48830.72, "durationSeconds": 5055.1, "drives": 3},
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
}


def replies() -> dict[str, Any]:
    """A fresh copy that a test can change."""
    return copy.deepcopy(REPLIES)
