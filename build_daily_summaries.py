#!/usr/bin/env python3
"""
build_daily_summaries.py — CCGL
Reads hourly-readings.json and computes daily aggregates (day/night/all)
per room per sensor. Writes to data/daily-summaries.json.

Light schedules:
  Flower 1: 07:00 – 19:00 (12h)
  Flower 2: 06:00 – 18:00 (12h)
  Mom:      08:00 – 01:30 (17.5h)
  Others:   treated as always-on

Run after every hourly fetch, or standalone.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent
HOURLY_FILE = BASE_DIR / "data" / "hourly-readings.json"
DAILY_FILE  = BASE_DIR / "data" / "daily-summaries.json"

# Light schedule: (lights_on_hour, lights_off_hour) in local time (ET = UTC-4 approx)
# Use 24h floats. Mom: 8.0 to 25.5 (wraps past midnight)
LIGHT_SCHEDULES = {
    "Flower 1": (7.0, 19.0),
    "Flower 2": (6.0, 18.0),
    "Mom":      (8.0, 25.5),  # 1:30 AM next day
}

UTC_OFFSET_HOURS = -4  # Eastern Daylight Time


def local_hour(ts_str):
    """Convert ISO timestamp string to local fractional hour."""
    # Parse ISO 8601 with Z or offset
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts_str)
    except ValueError:
        # Fallback: strip microseconds
        dt = datetime.fromisoformat(ts_str[:19] + "+00:00")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_dt = dt + timedelta(hours=UTC_OFFSET_HOURS)
    return local_dt, local_dt.strftime("%Y-%m-%d"), local_dt.hour + local_dt.minute / 60.0


def is_lights_on(room, hour_float):
    """Return True if lights are on for this room at this local hour."""
    if room not in LIGHT_SCHEDULES:
        return True  # No schedule = always treated as day
    on, off = LIGHT_SCHEDULES[room]
    if off <= 24:
        return on <= hour_float < off
    else:
        # Wraps past midnight (e.g. Mom: 8–25.5 means 8am–1:30am)
        return hour_float >= on or hour_float < (off - 24)


def merge_sensor(agg, value, min_val, max_val):
    """Merge one hourly reading into a running aggregate dict."""
    agg["sum"] = agg.get("sum", 0) + value
    agg["count"] = agg.get("count", 0) + 1
    agg["min"] = min(agg.get("min", float("inf")), min_val)
    agg["max"] = max(agg.get("max", float("-inf")), max_val)


def finalize(agg):
    """Convert running aggregate to {avg, min, max, count}."""
    if not agg or agg.get("count", 0) == 0:
        return {}
    return {
        "avg": round(agg["sum"] / agg["count"], 3),
        "min": round(agg["min"], 3),
        "max": round(agg["max"], 3),
        "count": agg["count"],
    }


def build_daily_summaries():
    # Load hourly readings
    if not HOURLY_FILE.exists():
        print("No hourly-readings.json found, skipping.")
        return

    with open(HOURLY_FILE) as f:
        readings = json.load(f)

    if not isinstance(readings, list) or not readings:
        print("hourly-readings.json is empty or wrong format.")
        return

    # Load existing daily summaries to preserve older dates
    if DAILY_FILE.exists():
        with open(DAILY_FILE) as f:
            existing = json.load(f)
    else:
        existing = {}

    # Build accumulators: {date: {room: {sensor: {day: agg, night: agg, all: agg}}}}
    accum = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"day": {}, "night": {}, "all": {}})))

    for entry in readings:
        ts = entry.get("timestamp", "")
        if not ts:
            continue
        try:
            local_dt, date_str, hour_float = local_hour(ts)
        except Exception:
            continue

        rooms = entry.get("rooms", {})
        for room, sensors in rooms.items():
            if not sensors:
                continue
            for sensor, data in sensors.items():
                if not isinstance(data, dict):
                    continue
                value = data.get("value")
                min_v = data.get("min", value)
                max_v = data.get("max", value)
                if value is None:
                    continue

                day_night = "day" if is_lights_on(room, hour_float) else "night"
                merge_sensor(accum[date_str][room][sensor][day_night], value, min_v, max_v)
                merge_sensor(accum[date_str][room][sensor]["all"],      value, min_v, max_v)

    # Finalize and merge into existing
    # Output format: {date: {room: {day: {sensor: stats}, night: {sensor: stats}, all: {sensor: stats}}}}
    # This matches what generate_email.py and generate_report.py expect (period-first, sensors inside)
    result = dict(existing)
    for date_str, rooms in accum.items():
        result[date_str] = {}
        for room, sensors in rooms.items():
            day_sensors   = {}
            night_sensors = {}
            all_sensors   = {}
            for sensor, periods in sensors.items():
                d = finalize(periods["day"])
                n = finalize(periods["night"])
                a = finalize(periods["all"])
                if d: day_sensors[sensor]   = d
                if n: night_sensors[sensor] = n
                if a: all_sensors[sensor]   = a
            result[date_str][room] = {
                "day":   day_sensors,
                "night": night_sensors,
                "all":   all_sensors,
            }

    # Sort by date
    result = dict(sorted(result.items()))

    with open(DAILY_FILE, "w") as f:
        json.dump(result, f, indent=2)

    dates = sorted(result.keys())
    print(f"✓ daily-summaries.json updated: {len(dates)} dates ({dates[0]} → {dates[-1]})")
    # Show quick room counts for latest date
    latest = dates[-1]
    for room in result[latest]:
        sensor_count = len(result[latest][room])
        sample = next(iter(result[latest][room].values()), {})
        all_count = sample.get("all", {}).get("count", 0)
        print(f"  {latest} {room}: {sensor_count} sensors, {all_count} hourly readings")


if __name__ == "__main__":
    build_daily_summaries()
