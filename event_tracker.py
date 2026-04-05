#!/usr/bin/env python3
"""
CCGL Event Persistence Tracker

Tracks cultivation events across hourly report cycles. Events persist
beyond individual snapshots to provide historical context.

Event lifecycle:
  1. ACTIVE    — condition currently flagged or recurred within 6 hours
  2. RESOLVED  — normalized for 6+ consecutive hours, visible for 48h
  3. ARCHIVED  — removed from report, kept in cycle log

Escalation: events flagged 3+ consecutive hours escalate in prominence.
Cycle log: compact summary of all major events per room/growth stage.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

EVENTS_PATH = Path(__file__).parent / "data" / "events.json"

# Thresholds that trigger events (room, sensor, condition, severity)
EVENT_RULES = [
    {
        "id": "high_humidity",
        "rooms": ["Flower 1", "Flower 2"],
        "sensor": "Ambient Humidity",
        "condition": "above",
        "threshold": 70,
        "severity": "warning",
        "label": "High Humidity",
        "description": "Elevated humidity increases botrytis risk in flower"
    },
    {
        "id": "extreme_humidity",
        "rooms": ["Flower 1", "Flower 2"],
        "sensor": "Ambient Humidity",
        "condition": "above",
        "threshold": 85,
        "severity": "critical",
        "label": "Extreme Humidity Spike",
        "description": "Dangerously high humidity — immediate botrytis risk"
    },
    {
        "id": "low_vpd",
        "rooms": ["Flower 1", "Flower 2"],
        "sensor": "Vapor Pressure Deficit",
        "condition": "below",
        "threshold": 0.8,
        "severity": "warning",
        "label": "Low VPD",
        "description": "VPD below optimal — reduced transpiration, moisture risk"
    },
    {
        "id": "high_vpd",
        "rooms": ["Flower 1", "Flower 2"],
        "sensor": "Vapor Pressure Deficit",
        "condition": "above",
        "threshold": 1.6,
        "severity": "warning",
        "label": "High VPD",
        "description": "VPD elevated — potential plant stress"
    },
    {
        "id": "substrate_dry",
        "rooms": ["Flower 1", "Flower 2", "Mom"],
        "sensor": "Substrate VWC",
        "condition": "below",
        "threshold": 15,
        "severity": "warning",
        "label": "Substrate Dry",
        "description": "VWC below 15% — irrigation may be insufficient"
    },
    {
        "id": "substrate_critical",
        "rooms": ["Flower 1", "Flower 2", "Mom"],
        "sensor": "Substrate VWC",
        "condition": "below",
        "threshold": 8,
        "severity": "critical",
        "label": "Substrate Critically Dry",
        "description": "VWC approaching permanent wilt point"
    },
    {
        "id": "high_temp",
        "rooms": ["Flower 1", "Flower 2", "Mom"],
        "sensor": "Ambient Temperature",
        "condition": "above",
        "threshold": 85,
        "severity": "warning",
        "label": "High Temperature",
        "description": "Temperature elevated — heat stress risk"
    },
    {
        "id": "low_temp",
        "rooms": ["Flower 1", "Flower 2", "Mom"],
        "sensor": "Ambient Temperature",
        "condition": "below",
        "threshold": 65,
        "severity": "warning",
        "label": "Low Temperature",
        "description": "Temperature below optimal — slowed metabolism"
    },
]

# Timing constants
RECURRENCE_WINDOW_H = 6     # Hours before a resolved event can reopen
RESOLVED_DISPLAY_H = 48     # Hours to show resolved events in report
ESCALATION_HOURS = 3        # Consecutive hours before escalation


def load_events():
    """Load events from disk, or return empty structure."""
    if EVENTS_PATH.exists():
        with open(EVENTS_PATH, 'r') as f:
            return json.load(f)
    return {"active": [], "resolved": [], "cycle_log": {}}


def save_events(events):
    """Save events to disk."""
    EVENTS_PATH.parent.mkdir(exist_ok=True)
    with open(EVENTS_PATH, 'w') as f:
        json.dump(events, f, indent=2)


def _now_iso():
    return datetime.now().astimezone().isoformat()


def _parse_dt(s):
    try:
        return datetime.fromisoformat(s)
    except:
        return datetime.now().astimezone()


def _hours_since(iso_str):
    dt = _parse_dt(iso_str)
    now = datetime.now().astimezone()
    return (now - dt).total_seconds() / 3600


def check_condition(value, condition, threshold):
    """Check if a sensor value triggers an event rule."""
    if value is None:
        return False
    if condition == "above":
        return value > threshold
    elif condition == "below":
        return value < threshold
    return False


def process_readings(state):
    """
    Main entry point: evaluate current sensor readings against event rules,
    update active/resolved events, and return the updated events structure.
    """
    events = load_events()
    now = _now_iso()
    rooms = state.get("current_readings", {}).get("rooms", {})
    growth_stages = state.get("growth_stages", {})

    # Track which events are currently triggered
    triggered = set()

    # --- Check each rule against current readings ---
    for rule in EVENT_RULES:
        for room_name in rule["rooms"]:
            room_data = rooms.get(room_name, {})
            sensor_data = room_data.get(rule["sensor"])
            if not sensor_data:
                continue

            value = sensor_data.get("value")
            if value is None:
                continue

            event_key = f"{room_name}::{rule['id']}"

            if check_condition(value, rule["condition"], rule["threshold"]):
                triggered.add(event_key)

                # Check if already active
                existing = next((e for e in events["active"] if e["key"] == event_key), None)

                if existing:
                    # Update existing active event
                    existing["last_seen"] = now
                    existing["current_value"] = value
                    existing["hours_active"] = _hours_since(existing["started"])
                    # Track peak
                    if rule["condition"] == "above" and value > existing.get("peak_value", value):
                        existing["peak_value"] = value
                        existing["peak_time"] = now
                    elif rule["condition"] == "below" and value < existing.get("peak_value", value):
                        existing["peak_value"] = value
                        existing["peak_time"] = now
                    # Only increment consecutive hours & log if 30+ min since last hourly entry
                    last_entry = existing.get("hourly_values", [{}])[-1] if existing.get("hourly_values") else {}
                    mins_since_last = _hours_since(last_entry.get("time", existing["started"])) * 60 if last_entry.get("time") else 999
                    if mins_since_last >= 30:
                        existing["consecutive_hours"] = existing.get("consecutive_hours", 1) + 1
                        existing.setdefault("hourly_values", [])
                        existing["hourly_values"].append({"time": now, "value": value})
                        existing["hourly_values"] = existing["hourly_values"][-72:]
                    # Escalation
                    if existing.get("consecutive_hours", 1) >= ESCALATION_HOURS:
                        existing["escalated"] = True
                else:
                    # Check if recently resolved (reopen if within window)
                    resolved_match = next(
                        (e for e in events["resolved"] if e["key"] == event_key
                         and _hours_since(e.get("resolved_at", now)) < RECURRENCE_WINDOW_H),
                        None
                    )

                    if resolved_match:
                        # Reopen — move back to active
                        resolved_match["status"] = "active"
                        resolved_match["last_seen"] = now
                        resolved_match["current_value"] = value
                        resolved_match["reopened_count"] = resolved_match.get("reopened_count", 0) + 1
                        resolved_match["consecutive_hours"] = 1
                        resolved_match.pop("resolved_at", None)
                        resolved_match.setdefault("hourly_values", []).append({"time": now, "value": value})
                        events["active"].append(resolved_match)
                        events["resolved"].remove(resolved_match)
                    else:
                        # New event
                        new_event = {
                            "key": event_key,
                            "room": room_name,
                            "rule_id": rule["id"],
                            "sensor": rule["sensor"],
                            "label": rule["label"],
                            "description": rule["description"],
                            "severity": rule["severity"],
                            "condition": rule["condition"],
                            "threshold": rule["threshold"],
                            "status": "active",
                            "started": now,
                            "last_seen": now,
                            "current_value": value,
                            "peak_value": value,
                            "peak_time": now,
                            "hours_active": 0,
                            "consecutive_hours": 1,
                            "escalated": False,
                            "reopened_count": 0,
                            "growth_stage": growth_stages.get(room_name, "Unknown"),
                            "hourly_values": [{"time": now, "value": value}]
                        }
                        events["active"].append(new_event)

    # --- Resolve events no longer triggered ---
    still_active = []
    for event in events["active"]:
        if event["key"] not in triggered:
            event["status"] = "resolved"
            event["resolved_at"] = now
            event["duration_hours"] = _hours_since(event["started"])
            events["resolved"].append(event)

            # Add to cycle log
            room = event["room"]
            stage = event.get("growth_stage", "Unknown")
            log_key = f"{room}::{stage}"
            events["cycle_log"].setdefault(log_key, [])
            events["cycle_log"][log_key].append({
                "label": event["label"],
                "severity": event["severity"],
                "started": event["started"],
                "resolved": now,
                "duration_hours": round(event.get("duration_hours", 0), 1),
                "peak_value": event.get("peak_value"),
                "peak_time": event.get("peak_time"),
                "reopened_count": event.get("reopened_count", 0),
                "sensor": event["sensor"]
            })
        else:
            still_active.append(event)
    events["active"] = still_active

    # --- Expire old resolved events (beyond display window) ---
    events["resolved"] = [
        e for e in events["resolved"]
        if _hours_since(e.get("resolved_at", now)) < RESOLVED_DISPLAY_H
    ]

    # --- Trim cycle log entries older than 60 days ---
    for log_key in list(events["cycle_log"].keys()):
        events["cycle_log"][log_key] = [
            entry for entry in events["cycle_log"][log_key]
            if _hours_since(entry.get("started", now)) < 60 * 24
        ]
        if not events["cycle_log"][log_key]:
            del events["cycle_log"][log_key]

    save_events(events)
    return events


def format_duration(hours):
    """Format hours into human-readable duration."""
    if hours < 1:
        return f"{int(hours * 60)}m"
    elif hours < 24:
        h = int(hours)
        m = int((hours - h) * 60)
        return f"{h}h {m}m" if m > 0 else f"{h}h"
    else:
        d = int(hours / 24)
        h = int(hours % 24)
        return f"{d}d {h}h" if h > 0 else f"{d}d"


def format_value(sensor, value):
    """Format a sensor value with units."""
    if "Temperature" in sensor:
        return f"{value:.1f}°F"
    elif "Humidity" in sensor:
        return f"{value:.1f}%"
    elif "CO2" in sensor:
        return f"{int(value)} ppm"
    elif "VPD" in sensor or "Deficit" in sensor:
        return f"{value:.2f} kPa"
    elif "VWC" in sensor:
        return f"{value:.1f}%"
    elif "EC" in sensor:
        return f"{value:.2f} dS/m"
    return f"{value:.1f}"


if __name__ == "__main__":
    # Test: load state and process
    state_path = Path(__file__).parent / "data" / "state.json"
    with open(state_path) as f:
        state = json.load(f)
    events = process_readings(state)
    print(f"Active events: {len(events['active'])}")
    for e in events["active"]:
        print(f"  [{e['severity'].upper()}] {e['room']}: {e['label']} — "
              f"{format_value(e['sensor'], e['current_value'])} "
              f"(started {e['started'][:16]}, {format_duration(e['hours_active'])})")
    print(f"Resolved events: {len(events['resolved'])}")
    for e in events["resolved"]:
        print(f"  [RESOLVED] {e['room']}: {e['label']} — "
              f"lasted {format_duration(e.get('duration_hours', 0))}")
    print(f"Cycle log entries: {sum(len(v) for v in events['cycle_log'].values())}")
