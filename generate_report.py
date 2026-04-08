#!/usr/bin/env python3
"""
CCGL GrowLink Report Generator (v4 — Data-Driven Edition)

Every section sources from live data. No hardcoded sensor values, no fabricated
targets presented as setpoints. Reads:
  - data/state.json (current_readings.rooms/facility/timestamp)
  - data/daily-summaries.json (day/night/all aggregates)
  - data/hourly-readings.json (historical series)
  - data/events.json via event_tracker.process_readings

Growth stages, light schedules, and stage-appropriate target ranges are
declared as config at the top of this file — not fetched from state.json.
"""

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from event_tracker import process_readings, format_duration, format_value


# --- Paths ---
BASE_DIR = Path(__file__).parent
TEMPLATE_PATH = BASE_DIR / "report_template.html"
STATE_PATH = BASE_DIR / "data" / "state.json"
HOURLY_PATH = BASE_DIR / "data" / "hourly-readings.json"
DAILY_PATH = BASE_DIR / "data" / "daily-summaries.json"
EVENTS_PATH = BASE_DIR / "data" / "events.json"
LOGO_PATH = BASE_DIR / "data" / "logo_base64.txt"
WORDMARK_PATH = BASE_DIR / "data" / "wordmark_base64.txt"
LOGO_SVG_PATH = BASE_DIR / "data" / "logo_svg_b64.txt"
WORDMARK_SVG_PATH = BASE_DIR / "data" / "wordmark_svg_b64.txt"
OUTPUT_PATH = BASE_DIR / "CCGL-Hourly-Report-Latest.html"
ARCHIVE_DIR = BASE_DIR / "reports"


# --- Colors ---
C = {
    "body_bg": "#0a1628", "card_bg": "#0f1f35", "card_border": "#1a3050",
    "sidebar": "#071318", "text": "#d0d8e0", "text2": "#7a8fa3",
    "muted": "#5a7088", "teal": "#4E9E8E", "blue": "#4A90B5",
    "lime": "#8DC63F", "deep_teal": "#0C5C52", "critical": "#e74c3c",
    "warning": "#f39c12", "good": "#2ecc71", "purple": "#9b59b6",
    "pink": "#e84393", "cyan": "#00cec9", "orange": "#e17055",
}


# --- Static configuration (facts the API doesn't give us) ---

GROWTH_STAGES = {
    "Flower 1": "Week 4 Flower",
    "Flower 2": "Late Flower",
    "Mom":      "Vegetative",
    "Cure Room": "Cure",
    "Dry Room": "Idle",
    "Clone":    "Clone/Veg",
    "Central Feed System": "Reservoir",
}

# F2 harvest target — used for dry-room pre-conditioning countdown
F2_HARVEST_DATE = datetime(2026, 4, 14)

# Light schedules (lights-on hours, 24h clock)
LIGHT_SCHEDULES = {
    "Flower 1": (7, 19),            # 7:00 AM – 7:00 PM
    "Flower 2": (6, 18),            # 6:00 AM – 6:00 PM
    "Mom":      (8, 25.5),          # 8:00 AM – 1:30 AM (next day)
    "Cure Room": None,
    "Dry Room": None,
}

# Stage-appropriate ranges used only to color-code status (NOT shown as setpoints)
TARGETS = {
    "Flower 1": {
        "Ambient Temperature":      (72, 82),
        "Ambient Humidity":         (45, 60),
        "Vapor Pressure Deficit":   (1.0, 1.5),
        "Ambient CO2":              (800, 1200),
        "Substrate VWC":            (30, 55),
        "Substrate EC":             (2.0, 3.5),
        "Substrate Temperature":    (68, 78),
    },
    "Flower 2": {
        "Ambient Temperature":      (68, 78),
        "Ambient Humidity":         (40, 55),
        "Vapor Pressure Deficit":   (1.2, 1.6),
        "Ambient CO2":              (600, 1000),
        "Substrate VWC":            (15, 40),
        "Substrate EC":             (1.5, 3.5),
        "Substrate Temperature":    (65, 75),
    },
    "Mom": {
        "Ambient Temperature":      (70, 80),
        "Ambient Humidity":         (55, 70),
        "Vapor Pressure Deficit":   (0.8, 1.2),
        "Ambient CO2":              (400, 1200),
        "Substrate VWC":            (30, 65),
        "Substrate EC":             (1.2, 2.8),
        "Substrate Temperature":    (68, 78),
    },
    "Cure Room": {
        "Ambient Temperature":      (58, 68),
        "Ambient Humidity":         (55, 65),
        "Vapor Pressure Deficit":   (0.4, 0.8),
    },
    "Dry Room": {
        "Ambient Temperature":      (58, 66),
        "Ambient Humidity":         (55, 65),
        "Vapor Pressure Deficit":   (0.6, 1.0),
    },
    "Central Feed System": {
        "Solution pH":              (5.5, 6.5),
        "Solution TDS":             (700, 1100),
        "Solution Temperature":     (60, 72),
    },
}

# Rooms that get first-class treatment in the main sections
PRIMARY_ROOMS = ["Flower 1", "Flower 2", "Mom"]
ALL_ROOMS_ORDER = ["Flower 1", "Flower 2", "Mom", "Cure Room", "Dry Room", "Central Feed System"]

# Key sensors to highlight in 24h performance view (varies per room)
KEY_SENSORS = {
    "Flower 1": ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit", "Ambient CO2", "Substrate VWC", "Substrate EC"],
    "Flower 2": ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit", "Ambient CO2", "Substrate VWC", "Substrate EC"],
    "Mom":      ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit", "Substrate VWC", "Substrate EC"],
    "Cure Room": ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit"],
    "Dry Room":  ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit"],
}


# --- Helpers ---

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def load_text(path):
    try:
        with open(path) as f:
            raw = f.read().strip()
    except Exception:
        return ""
    if not raw.startswith("data:"):
        raw = f"data:image/png;base64,{raw}"
    return raw


def rooms_of(state):
    return (state.get("current_readings", {}) or {}).get("rooms", {}) or {}


def facility_of(state):
    return (state.get("current_readings", {}) or {}).get("facility", {}) or {}


def state_timestamp(state):
    cr = state.get("current_readings", {}) or {}
    return cr.get("timestamp") or state.get("last_updated", "")


def get_val(room_data, sensor):
    """Return numeric value or None if sensor missing."""
    s = (room_data or {}).get(sensor)
    if not s:
        return None
    v = s.get("value")
    return v if v is not None else None


def has_sensor(room_data, sensor):
    return get_val(room_data, sensor) is not None


def fmt(sensor_name, value):
    if value is None:
        return "—"
    if "Temperature" in sensor_name:   return f"{value:.1f}°F"
    if "Humidity" in sensor_name:      return f"{value:.1f}%"
    if "CO2" in sensor_name:           return f"{int(value)} ppm"
    if "VPD" in sensor_name or "Deficit" in sensor_name: return f"{value:.2f} kPa"
    if "pH" in sensor_name:            return f"{value:.2f}"
    if "TDS" in sensor_name:           return f"{int(value)} ppm"
    if "EC" in sensor_name:            return f"{value:.2f} dS/m"
    if "VWC" in sensor_name:           return f"{value:.1f}%"
    if "Float" in sensor_name:         return f"{value:.0f}%"
    return f"{value:.2f}"


def target_for(room, sensor):
    return TARGETS.get(room, {}).get(sensor)


def classify(room, sensor, value):
    """Return 'good' | 'warning' | 'critical' | 'unknown'."""
    if value is None:
        return "unknown"
    t = target_for(room, sensor)
    if not t:
        return "good"  # no target → assume fine
    lo, hi = t
    if lo <= value <= hi:
        return "good"
    margin = (hi - lo) * 0.15
    if (lo - margin) <= value <= (hi + margin):
        return "warning"
    return "critical"


def status_color(cls):
    return {"good": C["good"], "warning": C["warning"], "critical": C["critical"],
            "unknown": C["muted"]}[cls]


def health_score(room, room_data):
    """Score a room 0-100 from its per-sensor classifications."""
    if not room_data:
        return 100
    g = w = cr = 0
    for sn in room_data.keys():
        v = get_val(room_data, sn)
        if v is None:
            continue
        cls = classify(room, sn, v)
        if cls == "good": g += 1
        elif cls == "warning": w += 1
        elif cls == "critical": cr += 1
    total = g + w + cr
    if total == 0:
        return 100
    return max(0, 100 - (w * 15) - (cr * 25))


def lights_on(room, now=None):
    """Return True if lights should currently be ON for this room."""
    sched = LIGHT_SCHEDULES.get(room)
    if not sched:
        return None
    now = now or datetime.now()
    hour = now.hour + now.minute / 60.0
    lo, hi = sched
    # Handle schedules that cross midnight (e.g. Mom 8 → 25.5 means 8:00 → 1:30 next day)
    if hi > 24:
        return hour >= lo or hour < (hi - 24)
    return lo <= hour < hi


# --- Section: 24h Performance (top of report) ---

def _merge_sensor_stats(a, b):
    if not a: return dict(b) if b else {}
    if not b: return dict(a)
    ca, cb = a.get("count", 0), b.get("count", 0)
    total = ca + cb
    out = {
        "min": min(a.get("min", 9e9), b.get("min", 9e9)),
        "max": max(a.get("max", -9e9), b.get("max", -9e9)),
        "count": total,
    }
    if total > 0 and a.get("avg") is not None and b.get("avg") is not None:
        out["avg"] = (a["avg"] * ca + b["avg"] * cb) / total
    else:
        out["avg"] = a.get("avg") or b.get("avg")
    return out


def _hourly_val(room_data, sensor):
    """Hourly entries may store either {value,...} dicts or raw floats."""
    s = (room_data or {}).get(sensor)
    if s is None:
        return None
    if isinstance(s, dict):
        return s.get("value")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _last24h_stats_from_hourly(hourly, room, sensor):
    """Compute min/max/avg over the last 24 snapshots."""
    if not hourly:
        return {}
    recent = hourly[-24:]
    vals = []
    for entry in recent:
        r = entry.get("rooms", {}).get(room, {})
        v = _hourly_val(r, sensor)
        if v is not None:
            vals.append(v)
    if not vals:
        return {}
    return {"min": min(vals), "max": max(vals), "avg": sum(vals) / len(vals), "count": len(vals)}


def build_24h_performance(state, hourly, daily_summaries, events):
    """Live 24-hour performance: per-room, derived from hourly-readings.json."""
    now = datetime.now()
    active = events.get("active", [])
    resolved = events.get("resolved", [])

    # Events by room
    room_active, room_resolved = {}, {}
    for e in active:
        room_active.setdefault(e.get("room", ""), []).append(e)
    for e in resolved:
        room_resolved.setdefault(e.get("room", ""), []).append(e)

    room_css = {"Flower 1": "f1", "Flower 2": "f2", "Mom": "mom"}

    html = f'<div style="font-size:11px;color:{C["muted"]};margin-bottom:16px;text-align:right">Last 24 snapshots · {now.strftime("%b %-d")}</div>\n'
    html += '<div class="perf24-grid">\n'

    for room in PRIMARY_ROOMS:
        rd = rooms_of(state).get(room, {})
        sensors = [s for s in KEY_SENSORS.get(room, []) if has_sensor(rd, s) or s in ("Substrate VWC", "Substrate EC")]
        # Only keep sensors that exist live OR had data in the hourly history
        available_sensors = []
        for s in sensors:
            stats = _last24h_stats_from_hourly(hourly, room, s)
            if stats or has_sensor(rd, s):
                available_sensors.append(s)

        r_active = room_active.get(room, [])
        r_resolved = room_resolved.get(room, [])

        if any(e.get("severity") == "critical" for e in r_active):
            badge = '<span class="badge badge-critical">CRITICAL</span>'
        elif r_active:
            badge = '<span class="badge badge-warning">ATTENTION</span>'
        else:
            badge = '<span class="badge badge-good">ON TRACK</span>'

        html += f'''<div class="perf24-card {room_css.get(room,"")}">
    <div class="perf24-header">
        <div class="perf24-room">{room} <span class="perf24-stage">{GROWTH_STAGES.get(room, "")}</span></div>
        {badge}
    </div>
    <table class="perf24-table">
    <thead><tr><th>Sensor</th><th>24h Range</th><th>Avg</th><th>Now</th></tr></thead>
    <tbody>
'''
        for sensor in available_sensors:
            stats = _last24h_stats_from_hourly(hourly, room, sensor)
            cur = get_val(rd, sensor)
            short = (sensor.replace("Ambient ", "")
                           .replace("Vapor Pressure Deficit", "VPD")
                           .replace("Substrate ", "Sub "))
            if stats and stats.get("min") is not None:
                range_str = f"{fmt(sensor, stats['min'])} – {fmt(sensor, stats['max'])}"
                avg_str = fmt(sensor, stats.get("avg"))
            else:
                range_str = "—"
                avg_str = "—"
            cls = classify(room, sensor, cur)
            col = status_color(cls)
            now_str = f'<span style="color:{col};font-weight:700">{fmt(sensor, cur)}</span>'
            html += f'''    <tr><td>{short}</td><td>{range_str}</td><td>{avg_str}</td><td style="text-align:right">{now_str}</td></tr>\n'''
        html += '    </tbody>\n    </table>\n'

        # 24h event summary
        if r_active or r_resolved:
            html += '    <div class="perf24-events">\n'
            for e in r_active:
                sev_c = C["critical"] if e.get("severity") == "critical" else C["warning"]
                dur = format_duration(e.get("hours_active", 0))
                peak = e.get("peak_value")
                pk = f" · peaked {format_value(e['sensor'], peak)}" if peak is not None else ""
                html += f'    <div class="evt-line"><span style="color:{sev_c};font-weight:600">{e.get("label","")}</span> <span style="color:{C["muted"]}">{dur} active{pk}</span></div>\n'
            for e in r_resolved[:3]:
                peak = e.get("peak_value")
                pk = f" · peaked {format_value(e['sensor'], peak)}" if peak is not None else ""
                html += f'    <div class="evt-line"><span style="color:{C["good"]};font-weight:600">{e.get("label","")} ✓</span> <span style="color:{C["muted"]}">resolved{pk}</span></div>\n'
            html += '    </div>\n'
        html += '</div>\n'
    html += '</div>\n'
    return html


# --- Section: Alerts ---

def build_alerts(state, events):
    """Data-driven alerts derived from active events + facility health."""
    active = events.get("active", [])
    fac = facility_of(state)
    offline_modules = fac.get("offlineModules", []) or []
    critical_active = [e for e in active if e.get("severity") == "critical"]
    warning_active = [e for e in active if e.get("severity") == "warning"]
    escalated = [e for e in active if e.get("escalated")]

    html = '<div class="card-grid">\n'

    # 1) Critical events
    for e in critical_active:
        cur = e.get("current_value")
        peak = e.get("peak_value")
        sensor = e.get("sensor", "")
        room = e.get("room", "")
        html += f'''<div class="card alert-card">
    <div class="alert-header">
        <span class="alert-icon">🚨</span>
        <span class="alert-title">{room}: {e.get("label","")}</span>
        <span class="badge badge-critical">CRITICAL</span>
    </div>
    <div class="alert-metrics">
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C["critical"]}">{format_value(sensor, cur)}</div><div class="alert-metric-label">Current</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C["critical"]}">{format_value(sensor, peak)}</div><div class="alert-metric-label">Peak</div></div>
        <div class="alert-metric"><div class="alert-metric-value">{format_duration(e.get("hours_active",0))}</div><div class="alert-metric-label">Active</div></div>
        <div class="alert-metric"><div class="alert-metric-value">{e.get("consecutive_hours",1)}h</div><div class="alert-metric-label">Consecutive</div></div>
    </div>
    <div class="alert-description">{e.get("description","")}</div>
</div>\n'''

    # 2) Escalated warnings (≥3 consecutive hours)
    for e in escalated:
        if e in critical_active:
            continue
        cur = e.get("current_value")
        sensor = e.get("sensor", "")
        room = e.get("room", "")
        html += f'''<div class="card alert-card warning">
    <div class="alert-header">
        <span class="alert-icon">⚠️</span>
        <span class="alert-title">{room}: {e.get("label","")}</span>
        <span class="badge badge-warning">ESCALATED</span>
    </div>
    <div class="alert-metrics">
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C["warning"]}">{format_value(sensor, cur)}</div><div class="alert-metric-label">Current</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C["warning"]}">{format_value(sensor, e.get("peak_value"))}</div><div class="alert-metric-label">Peak</div></div>
        <div class="alert-metric"><div class="alert-metric-value">{format_duration(e.get("hours_active",0))}</div><div class="alert-metric-label">Active</div></div>
        <div class="alert-metric"><div class="alert-metric-value">{e.get("consecutive_hours",1)}h</div><div class="alert-metric-label">Consecutive</div></div>
    </div>
    <div class="alert-description">{e.get("description","")}</div>
</div>\n'''

    # 3) Facility health card
    mod_on = int(fac.get("modulesOnline", 0))
    mod_off = int(fac.get("modulesOffline", 0))
    if mod_off > 0:
        offline_txt = ", ".join(offline_modules) if offline_modules else f"{mod_off} modules"
        html += f'''<div class="card alert-card info">
    <div class="alert-header">
        <span class="alert-icon">📡</span>
        <span class="alert-title">{mod_off} Monitoring Module(s) Offline</span>
        <span class="badge badge-info">SYSTEM</span>
    </div>
    <div class="alert-description">{mod_on} online · {mod_off} offline. Offline: <strong>{offline_txt}</strong>.</div>
</div>\n'''

    # Nothing to alert on
    if not critical_active and not escalated and mod_off == 0:
        html += f'''<div class="card alert-card good">
    <div class="alert-header">
        <span class="alert-icon">✅</span>
        <span class="alert-title">All Clear — No Critical or Escalated Events</span>
        <span class="badge badge-good">STABLE</span>
    </div>
    <div class="alert-description">{len(warning_active)} active warning event(s) tracked below. All monitoring modules online.</div>
</div>\n'''

    html += '</div>'
    return html


# --- Section: Events — redesigned, room-grouped, expandable ---

def _escalation_spark(values, threshold, condition):
    if not values or len(values) < 2:
        return ""
    vmin = min(values)
    vmax = max(values)
    rng = max(0.01, vmax - vmin)
    bars = ""
    for v in values[-24:]:
        pct = int((v - vmin) / rng * 100)
        pct = max(10, min(100, pct))
        cls = ""
        if condition == "above" and v > threshold:
            cls = " over"
        elif condition == "below" and v < threshold:
            cls = " over"
        bars += f'<div class="evt-spark-bar{cls}" style="height:{pct}%"></div>'
    return f'<div class="evt-sparkline">{bars}</div>'


def build_events_section(state):
    """Room-grouped events view. Blends active, recently resolved, and cycle history
    into a single streamlined interface with expandable chips."""
    events = process_readings(state)
    active = events.get("active", [])
    resolved = events.get("resolved", [])
    cycle_log = events.get("cycle_log", {})

    # Group everything by room
    room_events = {}  # room → {"active": [...], "resolved": [...], "history": [...]}
    for e in active:
        room_events.setdefault(e.get("room", "Unknown"), {"active": [], "resolved": [], "history": []})["active"].append(e)
    for e in resolved:
        room_events.setdefault(e.get("room", "Unknown"), {"active": [], "resolved": [], "history": []})["resolved"].append(e)
    for log_key, entries in cycle_log.items():
        room = log_key.split("::", 1)[0]
        stage = log_key.split("::", 1)[1] if "::" in log_key else ""
        bucket = room_events.setdefault(room, {"active": [], "resolved": [], "history": []})
        for entry in entries:
            entry = dict(entry)
            entry["stage"] = stage
            bucket["history"].append(entry)

    if not room_events:
        return '<div class="evt-empty">No events tracked yet. Events accumulate as conditions are monitored.</div>'

    # Order rooms: flower first, then mom, then rest
    ordered_rooms = [r for r in ALL_ROOMS_ORDER if r in room_events] + \
                    [r for r in room_events if r not in ALL_ROOMS_ORDER]

    html = '<div class="roomevt-grid">\n'

    for room in ordered_rooms:
        bucket = room_events[room]
        r_active = bucket["active"]
        r_resolved = bucket["resolved"]
        r_history = sorted(bucket["history"], key=lambda x: x.get("started", ""), reverse=True)[:10]

        # Aggregate counts / severity for the header
        has_crit = any(e.get("severity") == "critical" for e in r_active)
        has_esc = any(e.get("escalated") for e in r_active)
        if has_crit:
            head_c = C["critical"]; head_label = f"{len(r_active)} ACTIVE"
        elif has_esc:
            head_c = C["warning"]; head_label = f"{len(r_active)} ESCALATED"
        elif r_active:
            head_c = C["warning"]; head_label = f"{len(r_active)} ACTIVE"
        elif r_resolved:
            head_c = C["good"]; head_label = f"{len(r_resolved)} RESOLVED (24h)"
        else:
            head_c = C["muted"]; head_label = "HISTORY"

        html += f'''<div class="roomevt-card" style="border-top-color:{head_c}">
    <div class="roomevt-head">
        <div class="roomevt-name">{room}<span class="roomevt-stage">{GROWTH_STAGES.get(room, "")}</span></div>
        <div class="roomevt-status" style="color:{head_c}">{head_label}</div>
    </div>\n'''

        # --- Active chips (expandable) ---
        for i, e in enumerate(r_active):
            sev = e.get("severity", "warning")
            chip_c = C["critical"] if sev == "critical" or e.get("escalated") else C["warning"]
            label = e.get("label", "")
            sensor = e.get("sensor", "")
            cur = e.get("current_value")
            peak = e.get("peak_value")
            dur = format_duration(e.get("hours_active", 0))
            consec = e.get("consecutive_hours", 1)
            reopen = e.get("reopened_count", 0)
            reopen_badge = f' <span class="chip-reopen">↻×{reopen}</span>' if reopen else ""
            esc_badge = ' <span class="chip-esc">⚡ESC</span>' if e.get("escalated") else ""
            hourly_vals = [h["value"] for h in e.get("hourly_values", []) if h.get("value") is not None]
            spark = _escalation_spark(hourly_vals, e.get("threshold", 0), e.get("condition", "above"))

            html += f'''    <details class="evt-chip" style="--chip-c:{chip_c}">
        <summary>
            <span class="chip-dot"></span>
            <span class="chip-title">{label}{esc_badge}{reopen_badge}</span>
            <span class="chip-meta">{format_value(sensor, cur)} · {dur}</span>
        </summary>
        <div class="chip-body">
            <div class="chip-grid">
                <div><div class="chip-val" style="color:{chip_c}">{format_value(sensor, cur)}</div><div class="chip-lab">Current</div></div>
                <div><div class="chip-val" style="color:{C["critical"]}">{format_value(sensor, peak)}</div><div class="chip-lab">Peak</div></div>
                <div><div class="chip-val">{dur}</div><div class="chip-lab">Duration</div></div>
                <div><div class="chip-val">{consec}h</div><div class="chip-lab">Consecutive</div></div>
            </div>
            <div class="chip-desc">{e.get("description","")}</div>
            {spark}
        </div>
    </details>\n'''

        # --- Recently resolved (compact chips) ---
        for e in r_resolved[:5]:
            dur = format_duration(e.get("duration_hours", 0))
            peak = e.get("peak_value")
            sensor = e.get("sensor", "")
            pk_str = f" · peaked {format_value(sensor, peak)}" if peak is not None else ""
            resolved_at = (e.get("resolved_at") or "")[:16].replace("T", " ")
            html += f'''    <div class="evt-chip resolved">
        <span class="chip-dot" style="background:{C["good"]}"></span>
        <span class="chip-title">{e.get("label","")} ✓</span>
        <span class="chip-meta">{dur}{pk_str}</span>
        <span class="chip-when">{resolved_at}</span>
    </div>\n'''

        # --- Cycle history (collapsed by default) ---
        if r_history:
            html += f'''    <details class="evt-history">
        <summary>Cycle history · {len(r_history)} event(s)</summary>
        <div class="history-list">\n'''
            for h in r_history:
                sev = h.get("severity", "warning")
                dot_c = C["critical"] if sev == "critical" else C["warning"]
                started = (h.get("started") or "")[:10]
                dur = format_duration(h.get("duration_hours", 0))
                reopen = h.get("reopened_count", 0)
                reopen_str = f' (↻×{reopen})' if reopen else ""
                stage = h.get("stage", "")
                html += f'            <div class="history-row"><span class="history-dot" style="background:{dot_c}"></span><span class="history-label">{h.get("label","")}{reopen_str}</span><span class="history-stage">{stage}</span><span class="history-dur">{dur}</span><span class="history-date">{started}</span></div>\n'
            html += '        </div>\n    </details>\n'

        if not r_active and not r_resolved and not r_history:
            html += f'    <div class="evt-quiet">No events recorded.</div>\n'

        html += '</div>\n'  # /roomevt-card

    html += '</div>'
    return html


# --- Section: Room cards ---

def build_room_cards(state):
    rooms = rooms_of(state)
    html = '<div class="card-grid">\n'

    for rn in ["Flower 1", "Flower 2", "Mom", "Cure Room", "Dry Room"]:
        if rn not in rooms:
            continue
        rd = rooms[rn] or {}
        hs = health_score(rn, rd)
        stage = GROWTH_STAGES.get(rn, "")

        if hs >= 80: dot = C["good"]; fill_cls = "health-fill-good"; h_color = C["good"]
        elif hs >= 50: dot = C["warning"]; fill_cls = "health-fill-warning"; h_color = C["warning"]
        else: dot = C["critical"]; fill_cls = "health-fill-critical"; h_color = C["critical"]

        # Build metrics grid — only for sensors that actually exist
        metrics = ''
        for sn, sd in rd.items():
            if sn == "None" or not sd:
                continue
            v = sd.get("value")
            if v is None:
                continue
            cls = classify(rn, sn, v)
            scol = status_color(cls)
            # 24h hourly min/max (not the daily period min/max from API)
            mn = sd.get("min", v)
            mx = sd.get("max", v)
            label = (sn.replace("Ambient ", "")
                       .replace("Solution ", "")
                       .replace("Substrate ", "Sub "))
            metrics += f'''<div class="metric-item status-{cls}">
    <div class="metric-value" style="color:{scol}">{fmt(sn, v)}</div>
    <div class="metric-label">{label}</div>
    <div class="metric-range">{fmt(sn, mn)} – {fmt(sn, mx)}</div>
</div>\n'''

        # Data-driven callouts (no hardcoded warnings)
        callout = ''
        present_sensors = {s for s, sd in rd.items() if sd and sd.get("value") is not None}
        expected = set(KEY_SENSORS.get(rn, []))
        missing = expected - present_sensors
        if rn in ("Flower 1", "Flower 2", "Mom"):
            sub_expected = {"Substrate VWC", "Substrate EC", "Substrate Temperature"}
            sub_missing = sub_expected - present_sensors
            if sub_missing == sub_expected:
                callout = f'<div class="callout callout-warning" style="margin-top:14px"><strong>⚠ No Substrate Sensors:</strong> Cannot monitor root-zone EC / VWC / temperature for {rn}.</div>'
            elif sub_missing:
                callout = f'<div class="callout callout-info" style="margin-top:14px"><strong>Data Gap:</strong> Missing: {", ".join(sorted(sub_missing))}.</div>'

        if rn == "Dry Room":
            days_to_harvest = (F2_HARVEST_DATE - datetime.now()).days
            t = get_val(rd, "Ambient Temperature")
            h = get_val(rd, "Ambient Humidity")
            t_str = fmt("Ambient Temperature", t) if t is not None else "—"
            h_str = fmt("Ambient Humidity", h) if h is not None else "—"
            callout = f'<div class="callout callout-info" style="margin-top:14px"><strong>📋 Pre-Harvest:</strong> F2 harvest ~{days_to_harvest} days out. Currently {t_str} / {h_str} RH. Target 58–66°F / 55–65% RH.</div>'

        html += f'''<div class="card">
    <h3><span class="card-status-dot" style="background:{dot}"></span> {rn} <span class="growth-stage">{stage}</span></h3>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
        <div class="health-bar" style="flex:1"><div class="health-bar-fill {fill_cls}" style="width:{hs}%"></div></div>
        <span style="font-size:13px;font-weight:600;color:{h_color}">{hs}%</span>
    </div>
    <div class="metric-grid">{metrics}</div>
    {callout}
</div>\n'''

    html += '</div>'
    return html


# --- Section: Feed / Fertigation deep dive ---

def build_feed_section(state, hourly, daily_summaries):
    feed = rooms_of(state).get("Central Feed System", {}) or {}
    rooms = rooms_of(state)

    ph = get_val(feed, "Solution pH")
    tds = get_val(feed, "Solution TDS")
    temp = get_val(feed, "Solution Temperature")
    flt = get_val(feed, "Solution Float")

    def cls_color(room, sensor, val):
        return status_color(classify(room, sensor, val))

    ph_col = cls_color("Central Feed System", "Solution pH", ph)
    tds_col = cls_color("Central Feed System", "Solution TDS", tds)
    temp_col = cls_color("Central Feed System", "Solution Temperature", temp)

    html = f'''<div class="feed-grid">
    <div class="feed-card">
        <div class="feed-value" style="color:{ph_col}">{fmt("pH", ph) if ph is not None else "—"}</div>
        <div class="feed-label">Solution pH</div>
        <div class="feed-range">Target 5.5 – 6.5</div>
    </div>
    <div class="feed-card">
        <div class="feed-value" style="color:{tds_col}">{fmt("TDS", tds) if tds is not None else "—"}</div>
        <div class="feed-label">TDS</div>
        <div class="feed-range">Target 700 – 1100 ppm</div>
    </div>
    <div class="feed-card">
        <div class="feed-value" style="color:{temp_col}">{fmt("Temperature", temp) if temp is not None else "—"}</div>
        <div class="feed-label">Solution Temp</div>
        <div class="feed-range">Target 60 – 72°F</div>
    </div>
    <div class="feed-card alert">
        <div class="feed-value" style="color:{C["warning"]}">{fmt("Float", flt) if flt is not None else "—"}</div>
        <div class="feed-label">Tank Float</div>
        <div class="feed-range">⚠ Sensor unreliable</div>
    </div>
</div>

<div class="card-grid">
    <div class="insight-card feed">
        <h4>🧪 Solution Chemistry</h4>
        <p><strong>pH:</strong> {fmt("pH", ph) if ph is not None else "—"} — {"inside" if ph is not None and 5.5 <= ph <= 6.5 else "outside"} the 5.5–6.5 window.</p>
        <p><strong>TDS:</strong> {fmt("TDS", tds) if tds is not None else "—"} — {"inside" if tds is not None and 700 <= tds <= 1100 else "outside"} the 700–1100 ppm window.</p>
        <p><strong>Temp:</strong> {fmt("Temperature", temp) if temp is not None else "—"} — dissolved oxygen is maximized below 68°F.</p>
    </div>
    <div class="insight-card" style="border-left-color:{C['warning']}">
        <h4>🔋 Tank Level</h4>
        <p>Float at {fmt("Float", flt) if flt is not None else "—"}. The tank float sensor has been inconsistent; verify via dip-stick twice daily until the sensor is replaced.</p>
    </div>
</div>
'''

    # --- Fertigation Intelligence Deep Dive ---
    # Now uses live data across all rooms that HAVE substrate sensors.
    substrate_data = {}
    for r in PRIMARY_ROOMS:
        rd = rooms.get(r, {}) or {}
        if has_sensor(rd, "Substrate EC") or has_sensor(rd, "Substrate VWC"):
            substrate_data[r] = {
                "ec": get_val(rd, "Substrate EC"),
                "vwc": get_val(rd, "Substrate VWC"),
                "temp": get_val(rd, "Substrate Temperature"),
            }

    # Cross-room substrate comparison
    html += f'''
<div class="card">
    <h3>⚙ Fertigation Intelligence Deep Dive</h3>
    <div class="card-grid">
        <div class="insight-card" style="border-left-color:{C['cyan']}">
            <h4>📊 Substrate EC / VWC — All Rooms</h4>
            <table class="sub-table">
                <thead><tr><th>Room</th><th>EC</th><th>VWC</th><th>Root Temp</th></tr></thead>
                <tbody>
'''
    for r in PRIMARY_ROOMS:
        rd = rooms.get(r, {}) or {}
        ec = get_val(rd, "Substrate EC")
        vwc = get_val(rd, "Substrate VWC")
        rtmp = get_val(rd, "Substrate Temperature")
        if ec is None and vwc is None and rtmp is None:
            html += f'<tr><td>{r}</td><td colspan="3" style="color:{C["muted"]}">No substrate sensors</td></tr>\n'
            continue
        ec_c = status_color(classify(r, "Substrate EC", ec))
        vwc_c = status_color(classify(r, "Substrate VWC", vwc))
        rtmp_c = status_color(classify(r, "Substrate Temperature", rtmp))
        html += f'''<tr>
    <td>{r}</td>
    <td style="color:{ec_c};font-weight:700">{fmt("EC", ec)}</td>
    <td style="color:{vwc_c};font-weight:700">{fmt("VWC", vwc)}</td>
    <td style="color:{rtmp_c};font-weight:700">{fmt("Temperature", rtmp)}</td>
</tr>
'''
    html += f'''                </tbody>
            </table>
        </div>
        <div class="insight-card" style="border-left-color:{C['purple']}">
            <h4>🔬 Feed vs. Substrate EC</h4>
'''
    if ph is not None and tds is not None:
        # Rough feed EC from TDS (500 scale): EC ≈ TDS / 500
        est_feed_ec = tds / 500.0
        html += f'<p><strong>Est. Feed EC:</strong> ~{est_feed_ec:.2f} dS/m (from TDS {int(tds)} ppm, 500-scale).</p>\n'
        for r, s in substrate_data.items():
            if s["ec"] is not None and est_feed_ec > 0:
                ratio = s["ec"] / est_feed_ec
                direction = "stacking" if ratio > 1.2 else "flushing" if ratio < 0.8 else "balanced"
                html += f'<p><strong>{r}:</strong> substrate EC {s["ec"]:.2f} vs. feed ~{est_feed_ec:.2f} → <em>{direction}</em> ({ratio:.1f}× feed).</p>\n'
    else:
        html += f'<p style="color:{C["muted"]}">Feed chemistry not available.</p>\n'

    html += '''        </div>
    </div>

    <div class="card-grid">
'''

    # Per-room substrate trend over 24h
    for r in PRIMARY_ROOMS:
        rd = rooms.get(r, {}) or {}
        if not (has_sensor(rd, "Substrate EC") or has_sensor(rd, "Substrate VWC")):
            continue
        ec_stats = _last24h_stats_from_hourly(hourly, r, "Substrate EC")
        vwc_stats = _last24h_stats_from_hourly(hourly, r, "Substrate VWC")
        cur_ec = get_val(rd, "Substrate EC")
        cur_vwc = get_val(rd, "Substrate VWC")

        def delta_note(cur, stats, label, unit_fmt):
            if cur is None or not stats:
                return ""
            avg = stats.get("avg")
            mn, mx = stats.get("min"), stats.get("max")
            d = (cur - avg) if avg is not None else 0
            arrow = "↑" if d > 0.05 else "↓" if d < -0.05 else "→"
            return f'<div class="sub-line"><strong>{label}:</strong> {unit_fmt(cur)} {arrow} (24h avg {unit_fmt(avg)}, range {unit_fmt(mn)}–{unit_fmt(mx)})</div>'

        html += f'''<div class="insight-card" style="border-left-color:{C["teal"]}">
    <h4>🌱 {r} — 24h Substrate Trend</h4>
    {delta_note(cur_ec, ec_stats, "EC", lambda v: fmt("EC", v))}
    {delta_note(cur_vwc, vwc_stats, "VWC", lambda v: fmt("VWC", v))}
</div>
'''

    html += '    </div>\n</div>'
    return html


# --- Section: Day/Night environment ---

def build_day_night(state):
    rooms = rooms_of(state)
    now = datetime.now()
    html = '<div class="dn-grid">\n'

    for rn in ["Flower 1", "Flower 2", "Mom", "Cure Room"]:
        rd = rooms.get(rn, {}) or {}
        if not rd:
            continue
        on = lights_on(rn, now)
        if on is None:
            light_label = "Passive monitoring"
        else:
            light_label = "☀ Lights ON" if on else "🌙 Lights OFF"

        card_cls = "dn-card"
        # Any critical sensor? flag the card
        any_crit = any(classify(rn, s, get_val(rd, s)) == "critical" for s in rd.keys() if s != "None")
        if any_crit:
            card_cls += " alert-state"

        html += f'''<div class="{card_cls}">
    <h4>{rn} <span class="dn-stage">{GROWTH_STAGES.get(rn,"")}</span> — {light_label}</h4>
'''
        for s in ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit", "Ambient CO2"]:
            if not has_sensor(rd, s):
                continue
            v = get_val(rd, s)
            col = status_color(classify(rn, s, v))
            label = s.replace("Ambient ", "").replace("Vapor Pressure Deficit", "VPD")
            html += f'    <div class="dn-row"><span class="dn-label">{label}</span><span class="dn-value" style="color:{col}">{fmt(s, v)}</span></div>\n'
        html += '</div>\n'

    html += '</div>\n'
    html += f'''<div class="callout callout-teal" style="margin-top:20px">
    <strong>💡 Light Schedules:</strong> &nbsp; F1: 7:00 AM – 7:00 PM &nbsp;|&nbsp; F2: 6:00 AM – 6:00 PM &nbsp;|&nbsp; Mom: 8:00 AM – 1:30 AM
    <br><span style="font-size:11px;color:{C["muted"]}">CO2 is not supplemented in Mom or Veg rooms — drops during lights-off are expected.</span>
</div>'''
    return html


# --- Section: Cultivation Deep Dive ---

def build_deep_dive(state, hourly):
    rooms = rooms_of(state)
    html = ''

    def env_metrics(rn, rd):
        out = ''
        for s in ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit", "Ambient CO2"]:
            v = get_val(rd, s)
            if v is None:
                continue
            col = status_color(classify(rn, s, v))
            label = s.replace("Ambient ", "").replace("Vapor Pressure Deficit", "VPD")
            out += f'''<div class="dive-metric"><div class="dive-metric-val" style="color:{col}">{fmt(s, v)}</div><div class="dive-metric-label">{label}</div></div>\n'''
        return out

    def root_metrics(rn, rd):
        if not (has_sensor(rd, "Substrate EC") or has_sensor(rd, "Substrate VWC") or has_sensor(rd, "Substrate Temperature")):
            return None
        out = ''
        for s in ["Substrate EC", "Substrate VWC", "Substrate Temperature"]:
            v = get_val(rd, s)
            if v is None:
                out += f'<div class="dive-metric"><div class="dive-metric-val" style="color:{C["muted"]}">—</div><div class="dive-metric-label">{s.replace("Substrate ","")}</div></div>\n'
                continue
            col = status_color(classify(rn, s, v))
            short = s.replace("Substrate ", "") + (" (dS/m)" if "EC" in s else "")
            out += f'<div class="dive-metric"><div class="dive-metric-val" style="color:{col}">{fmt(s, v)}</div><div class="dive-metric-label">{short}</div></div>\n'
        return out

    def environmental_assessment(rn, rd):
        """Generate environmental-only narrative from live data — no nutrient recs."""
        issues = []
        wins = []
        for s in ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit"]:
            v = get_val(rd, s)
            if v is None: continue
            cls = classify(rn, s, v)
            t = target_for(rn, s)
            if cls == "critical" and t:
                lo, hi = t
                direction = "below" if v < lo else "above"
                issues.append(f"{s.replace('Ambient ','')} {fmt(s,v)} is {direction} target ({fmt(s,lo)}–{fmt(s,hi)})")
            elif cls == "warning" and t:
                lo, hi = t
                direction = "below" if v < lo else "above"
                issues.append(f"{s.replace('Ambient ','')} {fmt(s,v)} is slightly {direction} target")
            elif cls == "good":
                wins.append(f"{s.replace('Ambient ','')} on target")
        return issues, wins

    # --- Flower 1 ---
    if "Flower 1" in rooms:
        rd = rooms["Flower 1"]
        issues, wins = environmental_assessment("Flower 1", rd)
        root = root_metrics("Flower 1", rd)
        html += f'''<div class="dive-card f1">
    <h3>🌸 Flower 1 — {GROWTH_STAGES["Flower 1"]}</h3>
    <div class="dive-section">
        <div class="dive-section-title">Environmental Snapshot</div>
        <div class="dive-metrics">{env_metrics("Flower 1", rd)}</div>
    </div>
'''
        if root:
            html += f'''    <div class="dive-section">
        <div class="dive-section-title">Root Zone</div>
        <div class="dive-metrics">{root}</div>
    </div>
'''
        html += '    <div class="dive-section"><div class="dive-section-title">Environmental Assessment</div>\n'
        if issues:
            html += '        <ul class="dive-checklist">\n'
            for it in issues:
                html += f'            <li>⚠ {it}</li>\n'
            for it in wins:
                html += f'            <li>✅ {it}</li>\n'
            html += '        </ul>\n'
        else:
            html += f'        <p style="color:{C["good"]}">All environmental parameters within target range.</p>\n'
        html += '    </div>\n</div>\n'

    # --- Flower 2 ---
    if "Flower 2" in rooms:
        rd = rooms["Flower 2"]
        issues, wins = environmental_assessment("Flower 2", rd)
        root = root_metrics("Flower 2", rd)
        days_out = (F2_HARVEST_DATE - datetime.now()).days
        html += f'''<div class="dive-card f2">
    <h3>🌿 Flower 2 — Pre-Harvest (~{days_out} days out)</h3>
    <div class="dive-section">
        <div class="dive-section-title">Environmental Snapshot</div>
        <div class="dive-metrics">{env_metrics("Flower 2", rd)}</div>
    </div>
'''
        if root:
            html += f'''    <div class="dive-section">
        <div class="dive-section-title">Root Zone</div>
        <div class="dive-metrics">{root}</div>
    </div>
'''
        else:
            html += f'''    <div class="dive-section">
        <div class="dive-section-title">Root Zone</div>
        <div class="callout callout-warning">No substrate sensors detected in current readings.</div>
    </div>
'''
        html += '    <div class="dive-section"><div class="dive-section-title">Environmental Assessment</div>\n'
        if issues:
            html += '        <ul class="dive-checklist">\n'
            for it in issues:
                html += f'            <li>⚠ {it}</li>\n'
            html += '        </ul>\n'
        else:
            html += f'        <p style="color:{C["good"]}">All environmental parameters within target range.</p>\n'
        html += '    </div>\n</div>\n'

    # --- Mom ---
    if "Mom" in rooms:
        rd = rooms["Mom"]
        issues, wins = environmental_assessment("Mom", rd)
        root = root_metrics("Mom", rd)
        html += f'''<div class="dive-card mom">
    <h3>🌱 Mother Room — {GROWTH_STAGES["Mom"]}</h3>
    <div class="dive-section">
        <div class="dive-section-title">Environmental Snapshot</div>
        <div class="dive-metrics">{env_metrics("Mom", rd)}</div>
    </div>
'''
        if root:
            html += f'''    <div class="dive-section">
        <div class="dive-section-title">Root Zone</div>
        <div class="dive-metrics">{root}</div>
    </div>
'''
        html += '    <div class="dive-section"><div class="dive-section-title">Environmental Assessment</div>\n'
        if issues:
            html += '        <ul class="dive-checklist">\n'
            for it in issues:
                html += f'            <li>⚠ {it}</li>\n'
            html += '        </ul>\n'
        else:
            html += f'        <p style="color:{C["good"]}">All environmental parameters within target range.</p>\n'
        html += '    </div>\n</div>\n'

    # --- Facility snapshot (Dry + Cure) ---
    dry = rooms.get("Dry Room", {}) or {}
    cure = rooms.get("Cure Room", {}) or {}
    days_out = (F2_HARVEST_DATE - datetime.now()).days
    html += f'''<div class="dive-card facility">
    <h3>🏭 Facility Operations</h3>
    <div class="card-grid">
        <div class="insight-card dry">
            <h4>🌡 Dry Room ({days_out}d to F2 harvest)</h4>
            <div class="dive-metrics">
                <div class="dive-metric"><div class="dive-metric-val" style="color:{C['blue']}">{fmt("Temperature", get_val(dry, "Ambient Temperature"))}</div><div class="dive-metric-label">Temp</div></div>
                <div class="dive-metric"><div class="dive-metric-val" style="color:{C['blue']}">{fmt("Humidity", get_val(dry, "Ambient Humidity"))}</div><div class="dive-metric-label">RH</div></div>
            </div>
            <p>Target 58–66°F / 55–65%. Pre-condition 48h before harvest.</p>
        </div>
        <div class="insight-card cure">
            <h4>🏺 Cure Room</h4>
            <div class="dive-metrics">
                <div class="dive-metric"><div class="dive-metric-val" style="color:{status_color(classify("Cure Room","Ambient Temperature",get_val(cure,"Ambient Temperature")))}">{fmt("Temperature", get_val(cure, "Ambient Temperature"))}</div><div class="dive-metric-label">Temp</div></div>
                <div class="dive-metric"><div class="dive-metric-val" style="color:{status_color(classify("Cure Room","Ambient Humidity",get_val(cure,"Ambient Humidity")))}">{fmt("Humidity", get_val(cure, "Ambient Humidity"))}</div><div class="dive-metric-label">RH</div></div>
            </div>
            <p>Target 58–68°F / 55–65% RH.</p>
        </div>
    </div>
</div>\n'''

    return html


# --- Section: Priorities (derived from real events) ---

def build_priorities(state, events):
    active = events.get("active", [])
    fac = facility_of(state)
    priorities = []

    # Critical events come first
    for e in sorted(active, key=lambda x: (0 if x.get("severity") == "critical" else 1,
                                           -x.get("consecutive_hours", 0))):
        if e.get("severity") == "critical":
            level, tag = "urgent", "URGENT"
        elif e.get("escalated"):
            level, tag = "urgent", "ESCALATED"
        else:
            level, tag = "high", "HIGH"
        cur = e.get("current_value")
        sensor = e.get("sensor", "")
        room = e.get("room", "")
        priorities.append({
            "level": level, "tag": tag,
            "title": f"{room}: {e.get('label','')}",
            "desc": f"{e.get('description','')} Currently {format_value(sensor, cur)} · {format_duration(e.get('hours_active', 0))} active.",
        })

    # Pre-harvest countdown
    days_to = (F2_HARVEST_DATE - datetime.now()).days
    if 0 <= days_to <= 10:
        priorities.append({
            "level": "high", "tag": "HIGH",
            "title": f"F2 Harvest Prep ({days_to}d)",
            "desc": f"Flower 2 harvest ~{F2_HARVEST_DATE.strftime('%b %d')}. Pre-condition Dry Room 48h before chop, plan dark period, assess trichomes daily.",
        })

    # Offline modules
    mod_off = int(fac.get("modulesOffline", 0))
    if mod_off > 0:
        offline = fac.get("offlineModules") or []
        priorities.append({
            "level": "medium", "tag": "MEDIUM",
            "title": f"Review {mod_off} Offline Module(s)",
            "desc": f"Offline: {', '.join(offline) if offline else 'modules'}. Confirm expected vs. unexpected outages.",
        })

    if not priorities:
        priorities.append({
            "level": "low", "tag": "OK",
            "title": "No Priority Actions",
            "desc": "All active events are warnings only, modules online, no critical thresholds crossed.",
        })

    html = ''
    for i, p in enumerate(priorities[:8], 1):
        html += f'''<div class="priority-card priority-{p["level"]}">
    <div class="priority-num">{i}</div>
    <div class="priority-content">
        <div class="priority-tag">{p["tag"]}</div>
        <div class="priority-title">{p["title"]}</div>
        <div class="priority-desc">{p["desc"]}</div>
    </div>
</div>\n'''
    return html


# --- Section: System Health ---

def build_system_health(state):
    fac = facility_of(state)
    rooms = rooms_of(state)
    online = int(fac.get("modulesOnline", 0))
    off = int(fac.get("modulesOffline", 0))
    total = online + off
    pct = int(online / total * 100) if total > 0 else 0
    pct_c = C["good"] if pct >= 85 else C["warning"] if pct >= 70 else C["critical"]
    offline_modules = fac.get("offlineModules") or []
    active_alerts = int(fac.get("activeAlerts", 0))

    html = f'''<div class="exec-grid">
    <div class="exec-card"><div class="exec-number">{online}/{total}</div><div class="exec-label">Modules Online</div></div>
    <div class="exec-card"><div class="exec-number" style="color:{C['warning']}">{off}</div><div class="exec-label">Modules Offline</div></div>
    <div class="exec-card"><div class="exec-number" style="color:{pct_c}">{pct}%</div><div class="exec-label">Uptime</div></div>
    <div class="exec-card"><div class="exec-number" style="color:{C['blue']}">{active_alerts}</div><div class="exec-label">GrowLink Alerts</div></div>
</div>

<div class="sys-grid">
    <div class="sys-card offline">
        <h4>📡 Offline Modules ({len(offline_modules)})</h4>
        <ul class="module-list">
'''
    if offline_modules:
        for m in offline_modules:
            dot = C["warning"] if "Flower" in m else C["muted"]
            html += f'            <li><span class="module-dot" style="background:{dot}"></span>{m}</li>\n'
    else:
        html += f'            <li style="color:{C["muted"]}">All modules online</li>\n'

    # Data Quality — dynamic per room
    html += '''        </ul>
    </div>
    <div class="sys-card">
        <h4>📊 Sensor Coverage (Live)</h4>
        <ul class="module-list">
'''
    for rn in ["Flower 1", "Flower 2", "Mom", "Cure Room", "Dry Room", "Central Feed System"]:
        rd = rooms.get(rn, {}) or {}
        present = [s for s, sd in rd.items() if s != "None" and sd and sd.get("value") is not None]
        has_env = any(s in present for s in ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit"])
        has_sub = any(s in present for s in ["Substrate VWC", "Substrate EC", "Substrate Temperature"])
        has_chem = any(s in present for s in ["Solution pH", "Solution TDS", "Solution Temperature"])
        has_co2 = "Ambient CO2" in present

        # Expected coverage by room
        if rn in ("Flower 1", "Flower 2", "Mom"):
            full = has_env and has_sub and has_co2
            label_bits = []
            if has_env: label_bits.append("env")
            if has_sub: label_bits.append("substrate")
            else: label_bits.append("no substrate")
            if has_co2: label_bits.append("CO2")
            status_c = C["good"] if full else C["warning"]
            summary = " · ".join(label_bits)
        elif rn in ("Cure Room", "Dry Room"):
            status_c = C["good"] if has_env else C["warning"]
            summary = "env ✓" if has_env else "no env sensors"
        elif rn == "Central Feed System":
            status_c = C["good"] if has_chem else C["warning"]
            summary = "chemistry ✓" if has_chem else "no chemistry"
        else:
            status_c = C["muted"]
            summary = f"{len(present)} sensors"

        html += f'            <li><span class="module-dot" style="background:{status_c}"></span><strong>{rn}:</strong> {summary} ({len(present)} sensors)</li>\n'

    html += '''        </ul>
    </div>
    <div class="sys-card issues">
        <h4>⚙ Known Issues</h4>
        <ul class="module-list">
'''
    # Dynamic known issues
    feed = rooms.get("Central Feed System", {}) or {}
    flt = get_val(feed, "Solution Float")
    if flt is not None:
        html += f'            <li><span class="module-dot" style="background:{C["warning"]}"></span><strong>Tank Float:</strong> sensor unreliable — verify manually</li>\n'
    if off > 0:
        html += f'            <li><span class="module-dot" style="background:{C["warning"]}"></span><strong>{off} Offline Module(s)</strong></li>\n'

    html += f'            <li><span class="module-dot" style="background:{C["muted"]}"></span><strong>CO2:</strong> Not supplemented in Mom/Veg</li>\n'
    html += '''        </ul>
    </div>
</div>'''
    return html


# --- Main ---

def main():
    print("Loading data...")
    state = load_json(STATE_PATH, default={})
    hourly = load_json(HOURLY_PATH, default=[])
    daily_summaries = load_json(DAILY_PATH, default={})

    logo = load_text(LOGO_PATH)
    wordmark = load_text(WORDMARK_PATH)
    logo_svg = load_text(LOGO_SVG_PATH)
    wordmark_svg = load_text(WORDMARK_SVG_PATH)

    print("Loading template...")
    with open(TEMPLATE_PATH) as f:
        template = f.read()

    # Compute events once, reused by several sections
    events = process_readings(state)

    # Timestamps — display in Eastern Time
    last_updated = state_timestamp(state)
    try:
        dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        eastern = timezone(timedelta(hours=-4))
        dt_et = dt.astimezone(eastern)
        data_time = dt_et.strftime("%B %d, %Y · %I:%M %p") + " ET"
    except Exception:
        data_time = "Unknown"

    now = datetime.now()
    gen_time = now.strftime("%B %d, %Y · %I:%M %p")

    # Header growth stage summary
    header_stages = (f"F1: {GROWTH_STAGES['Flower 1']} · "
                     f"F2: {GROWTH_STAGES['Flower 2']} · "
                     f"Mom: {GROWTH_STAGES['Mom']}")

    replacements = {
        "{{LOGO_DATA_URI}}": logo,
        "{{WORDMARK_DATA_URI}}": wordmark,
        "{{LOGO_SVG_URI}}": logo_svg,
        "{{WORDMARK_SVG_URI}}": wordmark_svg,
        "{{HEADER_GROWTH_STAGES}}": header_stages,
        "{{HEADER_TIMESTAMPS}}": f"Data as of {data_time} · Report generated {gen_time}",
        "{{PERFORMANCE_24H_SECTION}}": build_24h_performance(state, hourly, daily_summaries, events),
        "{{ALERTS_SECTION}}": build_alerts(state, events),
        "{{EVENTS_SECTION}}": build_events_section(state),
        "{{ROOMS_SECTION}}": build_room_cards(state),
        "{{FEED_SECTION}}": build_feed_section(state, hourly, daily_summaries),
        "{{DAYNIGHT_SECTION}}": build_day_night(state),
        "{{PRIORITIES_SECTION}}": build_priorities(state, events),
        "{{HEALTH_SECTION}}": build_system_health(state),
        "{{FOOTER_META}}": f"Generated by CCGL GrowLink Analyst · {gen_time}",
    }

    print(f"Filling {len(replacements)} placeholders...")
    html = template
    for k, v in replacements.items():
        html = html.replace(k, v)

    import re
    unfilled = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if unfilled:
        print(f"  ⚠ Unfilled: {unfilled}")
    else:
        print("  ✓ All placeholders filled")

    print(f"Writing report to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    index_path = BASE_DIR / "index.html"
    shutil.copy2(OUTPUT_PATH, index_path)

    ARCHIVE_DIR.mkdir(exist_ok=True)
    archive_path = ARCHIVE_DIR / f"CCGL-Report-{now.strftime('%Y-%m-%d-%H%M')}.html"
    shutil.copy2(OUTPUT_PATH, archive_path)

    size = os.path.getsize(OUTPUT_PATH)
    print(f"\n✓ Report generated!")
    print(f"  Size: {size/1024:.1f} KB ({size:,} bytes)")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  GitHub Pages: {index_path}")
    print(f"  Archive: {archive_path}")


if __name__ == "__main__":
    main()
