#!/usr/bin/env python3
"""
CCGL GrowLink API Fetcher

Fetches live sensor data from the GrowLink portal API using a bearer token
stashed in data/config.json (captured from browser localStorage).

Outputs:
  - data/state.json       — current snapshot (last_updated + current_readings)
  - data/hourly-readings.json — appended with new entry (dedupe by hour)

This script runs on Dan's Mac (not in the Cowork sandbox) because the sandbox
egress proxy blocks Azure endpoints. Invoked from push_live.sh as step 0.

Exit codes:
  0  success
  1  missing/invalid config
  2  auth failure (token expired — need to refresh from browser)
  3  network/API error
"""

import json
import os
import sys
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"
HOURLY_PATH = DATA_DIR / "hourly-readings.json"

USER_API = "https://glprod-userapi2.azurewebsites.net"
# Fallback org id if not in config (matches the CCGL org id from the memory)
DEFAULT_ORG_ID = "fdc753ea-da00-4fc2-a4e2-c82e51f4757a"

# Rooms we care about (matches what appears in state.json)
ROOM_NAMES_OF_INTEREST = {
    "Central Feed System",
    "Clone",
    "Cure Room",
    "Dry Room",
    "Flower 1",
    "Flower 2",
    "Mom",
}

# Normalize sensor names to the canonical form the report code expects
SENSOR_NAME_ALIASES = {
    "VPD": "Vapor Pressure Deficit",
    "Ambient CO₂": "Ambient CO2",
}


def log(msg):
    print(f"[fetch_growlink] {msg}", flush=True)


def load_config():
    if not CONFIG_PATH.exists():
        log(f"ERROR: {CONFIG_PATH} not found — capture token from browser first")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    if not cfg.get("growlink_token"):
        log("ERROR: config.json missing 'growlink_token'")
        sys.exit(1)
    return cfg


def api_get(path, token):
    url = f"{USER_API}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "CCGL-Fetcher/1.0",
    })
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        log(f"HTTP {e.code} on {path}: {body}")
        if e.code in (401, 403):
            log("AUTH FAILURE — token likely expired. Re-capture from browser.")
            sys.exit(2)
        sys.exit(3)
    except urllib.error.URLError as e:
        log(f"NETWORK ERROR on {path}: {e.reason}")
        sys.exit(3)


def normalize_sensor_name(name):
    return SENSOR_NAME_ALIASES.get(name, name)


def transform_rooms(room_pages):
    """Turn the GrowLink RoomPages response into our internal rooms dict."""
    out = {}
    for room in room_pages or []:
        name = room.get("Name") or room.get("name") or ""
        if name not in ROOM_NAMES_OF_INTEREST:
            continue
        sensors = {}
        readings = room.get("LatestSensorReadings") or room.get("latestSensorReadings") or []
        for r in readings:
            stype = r.get("SensorTypeName") or r.get("sensorTypeName") or ""
            if not stype:
                continue
            stype = normalize_sensor_name(stype)
            val = r.get("Value") if r.get("Value") is not None else r.get("value")
            mn = r.get("MinValue") if r.get("MinValue") is not None else r.get("minValue")
            mx = r.get("MaxValue") if r.get("MaxValue") is not None else r.get("maxValue")
            if val is None:
                continue
            sensors[stype] = {
                "value": round(float(val), 2),
                "min": round(float(mn), 2) if mn is not None else round(float(val), 2),
                "max": round(float(mx), 2) if mx is not None else round(float(val), 2),
            }
        out[name] = sensors
    # Ensure all expected rooms have at least an empty dict so downstream code is happy
    for n in ROOM_NAMES_OF_INTEREST:
        out.setdefault(n, {})
    return out


def transform_facility(facility_page):
    """Extract facility health from the facility page response."""
    if not facility_page:
        return {"modulesOnline": 0, "modulesOffline": 0, "activeAlerts": 0,
                "totalAlerts": 0, "offlineModules": []}

    modules_online = facility_page.get("ModulesOnline") or facility_page.get("modulesOnline") or 0
    modules_offline = facility_page.get("ModulesOffline") or facility_page.get("modulesOffline") or 0

    module_status = facility_page.get("ModuleStatus") or facility_page.get("moduleStatus") or []
    offline_modules = []
    for m in module_status:
        online = m.get("IsOnline") if m.get("IsOnline") is not None else m.get("isOnline")
        if online is False:
            mname = m.get("Name") or m.get("name") or ""
            if mname:
                offline_modules.append(mname)

    alerts = facility_page.get("Alerts") or facility_page.get("alerts") or []
    active_alerts = facility_page.get("ActiveAlerts")
    if active_alerts is None:
        active_alerts = sum(1 for a in alerts if (a.get("IsActive") or a.get("isActive")))

    return {
        "modulesOnline": int(modules_online),
        "modulesOffline": int(modules_offline),
        "activeAlerts": int(active_alerts or 0),
        "totalAlerts": len(alerts),
        "offlineModules": offline_modules,
    }


def update_state(snapshot):
    state = {}
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH) as f:
                state = json.load(f)
        except Exception:
            state = {}
    state["last_updated"] = snapshot["timestamp"]
    state["current_readings"] = snapshot
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
    log(f"state.json updated @ {snapshot['timestamp']}")


def append_hourly(snapshot):
    entries = []
    if HOURLY_PATH.exists():
        try:
            with open(HOURLY_PATH) as f:
                entries = json.load(f)
        except Exception:
            entries = []

    new_entry = {"timestamp": snapshot["timestamp"], "rooms": snapshot["rooms"]}
    new_hour = snapshot["timestamp"][:13]  # YYYY-MM-DDTHH

    # Dedupe: if the latest entry is from the same hour, replace it
    if entries and entries[-1].get("timestamp", "")[:13] == new_hour:
        entries[-1] = new_entry
        log(f"hourly-readings: replaced same-hour entry for {new_hour}")
    else:
        entries.append(new_entry)
        log(f"hourly-readings: appended entry #{len(entries)} for {new_hour}")

    # Cap at 1500 entries (~60 days hourly)
    if len(entries) > 1500:
        entries = entries[-1500:]

    with open(HOURLY_PATH, "w") as f:
        json.dump(entries, f)


def main():
    cfg = load_config()
    token = cfg["growlink_token"]
    org_id = cfg.get("org_id") or DEFAULT_ORG_ID

    log(f"Fetching RoomPages for org {org_id[:8]}...")
    room_pages_resp = api_get(f"/api/pages/RoomPages/?organizationId={org_id}", token)

    log("Fetching facilitypages...")
    facility_resp = api_get(f"/api/pages/facilitypages?organizationId={org_id}", token)

    # The API may return the rooms either directly as a list, or wrapped in an object
    if isinstance(room_pages_resp, dict):
        room_list = (room_pages_resp.get("Rooms") or room_pages_resp.get("rooms")
                     or room_pages_resp.get("RoomPages") or [])
    else:
        room_list = room_pages_resp or []

    # Facility page might also be a list or dict — grab the first dict we find
    facility_page = facility_resp
    if isinstance(facility_resp, list):
        facility_page = facility_resp[0] if facility_resp else {}

    rooms = transform_rooms(room_list)
    facility = transform_facility(facility_page)

    snapshot = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "facility": facility,
        "rooms": rooms,
    }

    total_sensors = sum(len(v) for v in rooms.values())
    log(f"Got {len(rooms)} rooms, {total_sensors} sensor readings, "
        f"{facility['modulesOnline']} online / {facility['modulesOffline']} offline modules")

    update_state(snapshot)
    append_hourly(snapshot)
    log("✓ fetch complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
