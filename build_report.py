#!/usr/bin/env python3
"""
CCGL GrowLink Hourly Report Generator
Reads live data and generates a beautiful, professional HTML dashboard.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import math

# Configuration
FACILITY_NAME = "Cape Cod Grow Lab"
BASE_PATH = Path("/sessions/friendly-serene-meitner/mnt/CCGL Growlink Analyst")
DATA_DIR = BASE_PATH / "data"
STATE_FILE = DATA_DIR / "state.json"
HOURLY_FILE = DATA_DIR / "hourly-readings.json"
LOGO_FILE = Path("/sessions/friendly-serene-meitner/logo_b64.txt")
OUTPUT_FILE = BASE_PATH / "CCGL-Hourly-Report-Latest.html"
ARCHIVE_DIR = BASE_PATH / "reports"

# Room metadata
ROOM_META = {
    "Flower 1": {
        "stage": "Week 3 Flower (Day 22)",
        "schedule": {"start": 7, "end": 19},
        "type": "production",
    },
    "Flower 2": {
        "stage": "Late Flower (8 days to harvest)",
        "schedule": {"start": 6, "end": 18},
        "type": "production",
    },
    "Mom": {
        "stage": "Vegetative Mother Plants",
        "schedule": {"start": 8, "end": 25.5},
        "type": "propagation",
    },
    "Cure Room": {
        "stage": "Post-Harvest Curing",
        "schedule": {"start": None, "end": None},
        "type": "post_harvest",
    },
    "Dry Room": {
        "stage": "Idle (F2 harvest ~Apr 13)",
        "schedule": {"start": None, "end": None},
        "type": "post_harvest",
    },
    "Central Feed System": {
        "stage": "Nutrient Management",
        "schedule": None,
        "type": "support",
    },
}

# Optimal ranges
OPTIMAL_RANGES = {
    "Flower 1": {
        "day": {
            "Ambient Temperature": (68, 82),
            "Ambient Humidity": (45, 55),
            "Ambient CO2": (800, 1500),
            "Vapor Pressure Deficit": (1.0, 1.5),
        },
        "night": {
            "Ambient Temperature": (62, 72),
            "Ambient Humidity": (45, 55),
            "Ambient CO2": (800, 1500),
            "Vapor Pressure Deficit": (1.0, 1.5),
        },
    },
    "Flower 2": {
        "day": {
            "Ambient Temperature": (68, 82),
            "Ambient Humidity": (45, 55),
            "Ambient CO2": (800, 1500),
            "Vapor Pressure Deficit": (1.0, 1.5),
        },
        "night": {
            "Ambient Temperature": (62, 72),
            "Ambient Humidity": (45, 55),
            "Ambient CO2": (800, 1500),
            "Vapor Pressure Deficit": (1.0, 1.5),
        },
    },
    "Mom": {
        "Ambient Temperature": (75, 85),
        "Ambient Humidity": (55, 70),
        "Ambient CO2": (400, 2000),
        "Vapor Pressure Deficit": (0.8, 1.2),
    },
    "Cure Room": {
        "Ambient Temperature": (60, 70),
        "Ambient Humidity": (55, 65),
    },
    "Dry Room": {
        "Ambient Temperature": (60, 70),
        "Ambient Humidity": (55, 65),
    },
    "Central Feed System": {
        "Solution pH": (5.8, 6.5),
        "Solution Temperature": (65, 72),
        "Solution TDS": (600, 1400),
    },
}

KNOWN_BROKEN_MODULES = [
    "Clone Nutrient Module",
    "Clone Room Environment Module",
    "Environment Module 2",
    "Flower 2 PIC",
    "Veg Room PIC",
]


def load_json_file(filepath):
    """Load JSON file safely."""
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None


def load_logo_base64():
    """Load base64 encoded logo."""
    try:
        with open(LOGO_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None


def get_is_daytime(room_name, current_time):
    """Determine if it's daytime for a specific room based on light schedule."""
    if room_name not in ROOM_META or ROOM_META[room_name]["schedule"] is None:
        return None

    schedule = ROOM_META[room_name]["schedule"]
    if schedule["start"] is None or schedule["end"] is None:
        return False

    hour = current_time.hour + (current_time.minute / 60)

    if schedule["start"] < schedule["end"]:
        return schedule["start"] <= hour < schedule["end"]
    else:
        return hour >= schedule["start"] or hour < schedule["end"]


def get_status_color(value, min_val, max_val):
    """Get color status based on value and range."""
    if value is None:
        return "offline"

    target_low = min_val
    target_high = max_val
    range_size = target_high - target_low
    buffer = range_size * 0.15

    if target_low - buffer <= value <= target_high + buffer:
        return "good"
    elif target_low - (buffer * 2) <= value <= target_high + (buffer * 2):
        return "warning"
    else:
        return "critical"


def get_metric_status(room_name, sensor_name, value, is_daytime=None):
    """Determine metric status based on room, sensor, and current conditions."""
    if value is None:
        return "offline"

    ranges = None

    if room_name in OPTIMAL_RANGES:
        room_ranges = OPTIMAL_RANGES[room_name]

        if isinstance(room_ranges, dict) and "day" in room_ranges:
            if is_daytime is True:
                ranges = room_ranges.get("day", {}).get(sensor_name)
            elif is_daytime is False:
                ranges = room_ranges.get("night", {}).get(sensor_name)
            else:
                ranges = room_ranges.get("day", {}).get(sensor_name)
        else:
            ranges = room_ranges.get(sensor_name)

    if not ranges:
        return "neutral"

    min_val, max_val = ranges
    return get_status_color(value, min_val, max_val)


def calculate_health_score(room_name, sensors, is_daytime=None):
    """Calculate room health score 0-100."""
    if not sensors:
        return 0

    scores = []
    for sensor_name, sensor_data in sensors.items():
        value = sensor_data.get("value")
        if value is None:
            continue

        status = get_metric_status(room_name, sensor_name, value, is_daytime)

        if status == "good":
            scores.append(100)
        elif status == "warning":
            scores.append(70)
        elif status == "critical":
            scores.append(30)
        else:
            scores.append(50)

    if not scores:
        return 50
    return sum(scores) // len(scores)


def format_alert_description(alert_key, alert_data):
    """Convert raw alert data dict into a human-readable description."""
    key = alert_key.lower()
    desc = alert_data.get("description", "")
    if desc:
        return desc

    if "night_temp" in alert_data:
        return (f"Nighttime avg {alert_data['night_temp']:.1f}°F vs daytime avg {alert_data['day_temp']:.1f}°F "
                f"(differential: {alert_data['differential']:+.1f}°F). Plants require a 10–15°F drop at night for proper flower development.")
    elif "current_vwc" in alert_data:
        return f"Substrate VWC at {alert_data['current_vwc']}% — critically dry. Check sensor placement or trigger manual irrigation."
    elif "current_humidity" in alert_data:
        return (f"Humidity at {alert_data['current_humidity']}% (optimal: {alert_data.get('optimal_range', '45-55%')}). "
                f"VPD at {alert_data.get('vpd', 'N/A')} kPa. Elevated botrytis and mildew risk during flower.")
    elif "current_temp" in alert_data:
        opt = alert_data.get("optimal_night_temp_range", [62, 72])
        return (f"Temperature at {alert_data['current_temp']}°F — far above optimal night range "
                f"({opt[0]}–{opt[1]}°F). Likely HVAC failure. Inspect compressor and cooling system immediately.")
    elif "severity" in alert_data:
        return alert_data.get("description", f"Severity: {alert_data['severity']}")
    else:
        # Fallback: join key-value pairs
        parts = [f"{k}: {v}" for k, v in alert_data.items() if k != "status"]
        return ". ".join(str(p) for p in parts) if parts else "Alert triggered — investigate."


def build_action_items(state_data):
    """Build prioritized action items from anomalies and alerts."""
    items = []

    if "critical_alerts" in state_data:
        for alert_key, alert_data in state_data["critical_alerts"].items():
            if alert_data.get("status") == "CRITICAL":
                items.append({
                    "priority": "P0",
                    "title": alert_key.replace("_", " ").title(),
                    "description": format_alert_description(alert_key, alert_data),
                })
            elif alert_data.get("status") == "WARNING":
                items.append({
                    "priority": "P1",
                    "title": alert_key.replace("_", " ").title(),
                    "description": format_alert_description(alert_key, alert_data),
                })

    # Add known operational alerts
    if "known_issues" in state_data:
        for issue_key, issue_data in state_data.get("known_issues", {}).items():
            items.append({
                "priority": "P1",
                "title": issue_key.replace("_", " ").title(),
                "description": format_alert_description(issue_key, issue_data) if isinstance(issue_data, dict) else str(issue_data),
            })

    if "anomalies" in state_data:
        for anomaly in state_data["anomalies"]:
            if anomaly.get("deviation_pct", 0) > 40:
                items.append({
                    "priority": "P1",
                    "title": f"{anomaly['room']} — {anomaly['sensor']}",
                    "description": f"Current: {anomaly['current']}, 24h avg: {anomaly['avg_24h']:.1f} ({anomaly['deviation_pct']:.1f}% deviation)",
                })

    return items


def get_sensor_unit(sensor_name):
    """Get unit for sensor type."""
    units = {
        'Temperature': '°F',
        'Humidity': '%',
        'CO2': 'ppm',
        'pH': '',
        'TDS': 'ppm',
        'EC': 'dS/m',
        'VWC': '%',
        'Float': 'mm',
        'Vapor Pressure Deficit': 'kPa',
        'Light Level': 'µmol/m²/s',
    }
    for key, unit in units.items():
        if key in sensor_name:
            return unit
    return ''


def get_facility_status(facility):
    """Get overall facility status."""
    if facility.get('activeAlerts', 0) > 0:
        return 'Attention Required'
    elif facility.get('modulesOffline', 0) > 2:
        return 'Degraded'
    else:
        return 'Optimal'


def get_status_class(alert_count):
    """Get status class based on alert count."""
    if alert_count == 0:
        return 'good'
    elif alert_count < 3:
        return 'warning'
    else:
        return 'critical'


def render_alerts_section(action_items):
    """Render critical alerts section."""
    if not action_items:
        return '<div class="alerts-section"><div class="section-header">Critical Alerts</div><p class="no-data">No critical alerts at this time.</p></div>'

    alerts_html = '<div class="alerts-section"><div class="section-header">Critical Alerts</div>'
    for item in sorted(action_items, key=lambda x: {'P0': 0, 'P1': 1, 'P2': 2}.get(x['priority'], 3)):
        priority_class = 'p0' if item['priority'] == 'P0' else ('p1' if item['priority'] == 'P1' else 'p2')
        alerts_html += f'<div class="alert {priority_class}"><div><span class="alert-priority">{item["priority"]}</span><span class="alert-title">{item["title"]}</span></div><div class="alert-description">{item["description"]}</div></div>'
    alerts_html += '</div>'
    return alerts_html


def render_room_cards(rooms, current_time):
    """Render room status cards."""
    html = ''
    for room_name in sorted(rooms.keys()):
        room_data = rooms[room_name]
        sensors = room_data.get('sensors', {})
        is_daytime = get_is_daytime(room_name, current_time)
        health = calculate_health_score(room_name, sensors, is_daytime)

        meta = ROOM_META.get(room_name, {})
        stage = meta.get('stage', '')

        # Status badges
        status_badges = ''
        if is_daytime is not None:
            day_text = 'DAY' if is_daytime else 'NIGHT'
            badge_class = 'day' if is_daytime else 'night'
            status_badges += f'<span class="status-badge {badge_class}">{day_text}</span>'
        status_badges += f'<span class="status-badge health">Health: {health}%</span>'

        # Sensor items
        sensor_html = ''
        for sensor_name, sensor_data in sensors.items():
            value = sensor_data.get('value')
            min_val = sensor_data.get('min')
            max_val = sensor_data.get('max')

            if value is None:
                continue

            status = get_metric_status(room_name, sensor_name, value, is_daytime)
            unit = get_sensor_unit(sensor_name)

            range_str = f'{min_val:.1f}-{max_val:.1f}' if min_val and max_val else ''
            range_html = f'<span class="value-range">{range_str}</span>' if range_str else ''

            sensor_html += f'<div class="sensor-item"><span class="sensor-name">{sensor_name}</span><div class="sensor-value"><span class="value-display">{value:.1f}<span class="value-unit">{unit}</span></span><span class="status-indicator {status}"></span>{range_html}</div></div>'

        sensor_list_content = sensor_html if sensor_html else '<p class="no-data">No sensor data available</p>'

        html += f'<div class="room-card"><div class="room-header"><div class="room-name">{room_name}</div><div class="room-stage">{stage}</div><div class="room-status-line">{status_badges}</div><div class="health-bar"><div class="health-fill" style="width: {health}%"></div></div></div><div class="room-body"><div class="sensor-list">{sensor_list_content}</div></div></div>'

    return html


def render_trends_section(trends):
    """Render trends analysis table."""
    if not trends:
        return '<div class="trends-section"><div class="section-header">Trend Analysis</div><p class="no-data">No trend data available</p></div>'

    html = '<div class="trends-section"><div class="section-header">24-Hour Trend Analysis</div>'
    html += '<table class="trends-table"><thead><tr><th>Room</th><th>Sensor</th><th>1h Change</th><th>3h Change</th><th>6h Change</th><th>24h Change</th></tr></thead><tbody>'

    for room_name, room_trends in sorted(trends.items()):
        for sensor_name, time_trends in room_trends.items():
            for period in ['1h', '3h', '6h', '1d']:
                period_data = time_trends.get(period, {})
                pct = period_data.get('pct', 0)
                if pct > 5:
                    arrow = '<span class="trend-arrow trend-up">↑</span>'
                elif pct < -5:
                    arrow = '<span class="trend-arrow trend-down">↓</span>'
                else:
                    arrow = '<span class="trend-arrow">→</span>'

                if period == '1h':
                    trend_1h = f'<td><span class="trend-value">{arrow} {pct:+.1f}%</span></td>'
                elif period == '3h':
                    trend_3h = f'<td><span class="trend-value">{arrow} {pct:+.1f}%</span></td>'
                elif period == '6h':
                    trend_6h = f'<td><span class="trend-value">{arrow} {pct:+.1f}%</span></td>'
                else:
                    trend_24h = f'<td><span class="trend-value">{arrow} {pct:+.1f}%</span></td>'

            html += f'<tr><td>{room_name}</td><td>{sensor_name}</td>{trend_1h}{trend_3h}{trend_6h}{trend_24h}</tr>'

    html += '</tbody></table></div>'
    return html


def render_offline_modules_section(offline_modules):
    """Render offline modules section."""
    truly_offline = [m for m in offline_modules if m not in KNOWN_BROKEN_MODULES]

    if not truly_offline and len(offline_modules) == len(KNOWN_BROKEN_MODULES):
        html = '<div class="section-spacer"><div class="section-header">System Status</div>'
        html += '<p style="color: var(--color-text-secondary); margin: var(--spacing-md) 0;">The following modules are expected to be offline:</p><ul style="color: var(--color-text-secondary); margin-left: var(--spacing-lg);">'
        for module in KNOWN_BROKEN_MODULES:
            html += f'<li>{module}</li>'
        html += '</ul></div>'
        return html

    if truly_offline:
        html = '<div class="alerts-section"><div class="section-header">Unexpected Offline Modules</div>'
        for module in truly_offline:
            html += f'<div class="alert p1"><span class="alert-priority">P1</span><span class="alert-title">{module}</span><span class="alert-description">Module is offline and requires attention</span></div>'
        html += '</div>'
        return html

    return ''


def build_full_html(state_data, hourly_data, logo_b64):
    """Build the complete HTML document."""
    current_readings = state_data.get('current_readings', {})
    facility = current_readings.get('facility', {})
    rooms = current_readings.get('rooms', {})
    timestamp_str = current_readings.get('timestamp_edt', '')

    try:
        current_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except:
        current_time = datetime.now()

    action_items = build_action_items(state_data)
    facility_status = get_facility_status(facility)
    status_class = get_status_class(facility.get('activeAlerts', 0))
    modules_status = 'good' if facility.get('modulesOnline', 0) > facility.get('modulesOffline', 0) else 'warning'
    system_efficiency = state_data.get('facility_health', {}).get('system_efficiency', 'N/A')
    report_time = current_time.strftime('%H:%M EDT')
    generation_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S EDT')

    alerts_html = render_alerts_section(action_items)
    rooms_html = render_room_cards(rooms, current_time)
    trends_html = render_trends_section(state_data.get('trends', {}))
    modules_html = render_offline_modules_section(facility.get('offlineModules', []))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CCGL GrowLink Hourly Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        :root {{
            --color-bg: #000000;
            --color-bg-card: #070707;
            --color-border: #151515;
            --color-text-primary: #e0e0e0;
            --color-text-secondary: #888888;
            --color-text-heading: #ffffff;
            --color-teal: #4E9E8E;
            --color-ocean: #4A90B5;
            --color-lime: #8DC63F;
            --color-deep-teal: #0C5C52;
            --color-good: #2ecc71;
            --color-warning: #f39c12;
            --color-critical: #e74c3c;
            --color-neutral: #666666;
            --spacing-xs: 0.5rem;
            --spacing-sm: 1rem;
            --spacing-md: 1.5rem;
            --spacing-lg: 2rem;
            --spacing-xl: 3rem;
            --radius: 8px;
            --transition: all 0.3s ease;
        }}

        body {{
            background-color: var(--color-bg);
            color: var(--color-text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            font-size: 14px;
        }}

        a {{
            color: var(--color-ocean);
            text-decoration: none;
            transition: var(--transition);
        }}

        a:hover {{
            color: var(--color-teal);
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: var(--spacing-lg);
        }}

        .header {{
            text-align: center;
            margin-bottom: var(--spacing-xl);
            padding-bottom: var(--spacing-lg);
            border-bottom: 1px solid var(--color-border);
        }}

        .logo {{
            width: 120px;
            height: 120px;
            margin: 0 auto var(--spacing-md);
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .logo img {{
            max-width: 100%;
            max-height: 100%;
        }}

        .header h1 {{
            font-size: 2.5rem;
            color: var(--color-text-heading);
            margin-bottom: var(--spacing-xs);
            font-weight: 600;
        }}

        .header p {{
            color: var(--color-text-secondary);
            font-size: 1rem;
            margin-bottom: var(--spacing-sm);
        }}

        .header-meta {{
            display: flex;
            justify-content: center;
            gap: var(--spacing-lg);
            margin-top: var(--spacing-md);
            flex-wrap: wrap;
            font-size: 0.9rem;
        }}

        .meta-item {{
            display: flex;
            align-items: center;
            gap: var(--spacing-xs);
        }}

        .meta-badge {{
            background-color: var(--color-border);
            padding: var(--spacing-xs) var(--spacing-sm);
            border-radius: calc(var(--radius) / 2);
            color: var(--color-text-primary);
        }}

        .status-bar {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: var(--spacing-md);
            margin-bottom: var(--spacing-xl);
        }}

        .status-card {{
            background-color: var(--color-bg-card);
            border: 1px solid var(--color-border);
            border-radius: var(--radius);
            padding: var(--spacing-md);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .status-card-label {{
            color: var(--color-text-secondary);
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .status-card-value {{
            color: var(--color-text-heading);
            font-size: 1.8rem;
            font-weight: 600;
        }}

        .status-card.good {{
            border-left: 3px solid var(--color-good);
        }}

        .status-card.warning {{
            border-left: 3px solid var(--color-warning);
        }}

        .status-card.critical {{
            border-left: 3px solid var(--color-critical);
        }}

        .alerts-section {{
            margin-bottom: var(--spacing-xl);
        }}

        .section-header {{
            font-size: 1.3rem;
            color: var(--color-text-heading);
            margin-bottom: var(--spacing-md);
            display: flex;
            align-items: center;
            gap: var(--spacing-sm);
            font-weight: 600;
        }}

        .section-header::before {{
            content: '';
            width: 4px;
            height: 1.5rem;
            background-color: var(--color-teal);
            border-radius: 2px;
        }}

        .alert {{
            background-color: var(--color-bg-card);
            border-left: 4px solid;
            border-radius: var(--radius);
            padding: var(--spacing-md);
            margin-bottom: var(--spacing-sm);
        }}

        .alert.p0 {{
            border-left-color: var(--color-critical);
        }}

        .alert.p1 {{
            border-left-color: var(--color-warning);
        }}

        .alert.p2 {{
            border-left-color: var(--color-teal);
        }}

        .alert-priority {{
            display: inline-block;
            background-color: var(--color-border);
            color: var(--color-text-heading);
            padding: var(--spacing-xs) calc(var(--spacing-xs) * 1.5);
            border-radius: calc(var(--radius) / 2);
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            margin-right: var(--spacing-sm);
        }}

        .alert.p0 .alert-priority {{
            background-color: var(--color-critical);
        }}

        .alert.p1 .alert-priority {{
            background-color: var(--color-warning);
        }}

        .alert-title {{
            color: var(--color-text-heading);
            font-weight: 600;
            margin-bottom: var(--spacing-xs);
        }}

        .alert-description {{
            color: var(--color-text-secondary);
            font-size: 0.9rem;
        }}

        .rooms-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: var(--spacing-lg);
            margin-bottom: var(--spacing-xl);
        }}

        .room-card {{
            background-color: var(--color-bg-card);
            border: 1px solid var(--color-border);
            border-radius: var(--radius);
            overflow: hidden;
            transition: var(--transition);
        }}

        .room-card:hover {{
            border-color: var(--color-teal);
            box-shadow: 0 0 20px rgba(78, 158, 142, 0.1);
        }}

        .room-header {{
            background: linear-gradient(135deg, var(--color-deep-teal) 0%, var(--color-teal) 100%);
            padding: var(--spacing-md);
            border-bottom: 1px solid var(--color-border);
        }}

        .room-name {{
            font-size: 1.2rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: var(--spacing-xs);
        }}

        .room-stage {{
            font-size: 0.85rem;
            color: rgba(255, 255, 255, 0.8);
        }}

        .room-status-line {{
            display: flex;
            gap: var(--spacing-sm);
            margin-top: var(--spacing-sm);
            flex-wrap: wrap;
        }}

        .status-badge {{
            display: inline-block;
            padding: var(--spacing-xs) var(--spacing-sm);
            border-radius: calc(var(--radius) / 2);
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            white-space: nowrap;
        }}

        .status-badge.day {{
            background-color: var(--color-lime);
            color: #000;
        }}

        .status-badge.night {{
            background-color: #1a3a4a;
            color: var(--color-lime);
        }}

        .status-badge.health {{
            background-color: var(--color-border);
            color: var(--color-text-primary);
        }}

        .health-bar {{
            width: 100%;
            height: 4px;
            background-color: var(--color-border);
            border-radius: 2px;
            overflow: hidden;
            margin-top: var(--spacing-xs);
        }}

        .health-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--color-lime), var(--color-teal));
            transition: width 0.5s ease;
        }}

        .room-body {{
            padding: var(--spacing-md);
        }}

        .sensor-list {{
            display: flex;
            flex-direction: column;
            gap: var(--spacing-sm);
        }}

        .sensor-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: var(--spacing-sm);
            background-color: rgba(255, 255, 255, 0.02);
            border-radius: calc(var(--radius) / 2);
            border: 1px solid var(--color-border);
        }}

        .sensor-name {{
            font-size: 0.9rem;
            color: var(--color-text-secondary);
        }}

        .sensor-value {{
            text-align: right;
        }}

        .value-display {{
            font-weight: 600;
            font-size: 1rem;
            color: var(--color-text-heading);
        }}

        .value-unit {{
            font-size: 0.8rem;
            color: var(--color-text-secondary);
            margin-left: var(--spacing-xs);
        }}

        .value-range {{
            font-size: 0.8rem;
            color: var(--color-text-secondary);
            display: block;
            margin-top: 2px;
        }}

        .status-indicator {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-left: var(--spacing-sm);
            display: inline-block;
        }}

        .status-indicator.good {{
            background-color: var(--color-good);
        }}

        .status-indicator.warning {{
            background-color: var(--color-warning);
        }}

        .status-indicator.critical {{
            background-color: var(--color-critical);
        }}

        .status-indicator.neutral {{
            background-color: var(--color-neutral);
        }}

        .trends-section {{
            margin-bottom: var(--spacing-xl);
        }}

        .trends-table {{
            width: 100%;
            border-collapse: collapse;
            background-color: var(--color-bg-card);
            border: 1px solid var(--color-border);
            border-radius: var(--radius);
            overflow: hidden;
        }}

        .trends-table thead {{
            background-color: var(--color-border);
        }}

        .trends-table th {{
            padding: var(--spacing-md);
            text-align: left;
            font-weight: 600;
            color: var(--color-text-heading);
            border-bottom: 1px solid var(--color-border);
        }}

        .trends-table td {{
            padding: var(--spacing-md);
            border-bottom: 1px solid var(--color-border);
            color: var(--color-text-primary);
        }}

        .trends-table tr:hover {{
            background-color: rgba(78, 158, 142, 0.05);
        }}

        .trend-value {{
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 0.85rem;
        }}

        .trend-arrow {{
            display: inline-block;
            width: 16px;
            text-align: center;
            margin-right: 4px;
        }}

        .trend-up {{
            color: var(--color-critical);
        }}

        .trend-down {{
            color: var(--color-good);
        }}

        .footer {{
            text-align: center;
            padding-top: var(--spacing-lg);
            border-top: 1px solid var(--color-border);
            color: var(--color-text-secondary);
            font-size: 0.85rem;
            margin-top: var(--spacing-xl);
        }}

        .footer-link {{
            display: inline-block;
            margin: var(--spacing-sm) var(--spacing-md);
            padding: var(--spacing-sm) var(--spacing-md);
            background-color: var(--color-border);
            border: 1px solid var(--color-border);
            border-radius: calc(var(--radius) / 2);
            color: var(--color-ocean);
            transition: var(--transition);
        }}

        .footer-link:hover {{
            background-color: var(--color-teal);
            color: #ffffff;
        }}

        @media (max-width: 768px) {{
            .container {{
                padding: var(--spacing-md);
            }}

            .header h1 {{
                font-size: 1.8rem;
            }}

            .rooms-grid {{
                grid-template-columns: 1fr;
            }}

            .status-bar {{
                grid-template-columns: 1fr;
            }}

            .header-meta {{
                flex-direction: column;
                gap: var(--spacing-sm);
            }}
        }}

        .no-data {{
            color: var(--color-text-secondary);
            font-style: italic;
        }}

        .section-spacer {{
            margin-bottom: var(--spacing-xl);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <img src="data:image/png;base64,{logo_b64}" alt="CCGL Logo" />
            </div>
            <h1>{FACILITY_NAME}</h1>
            <p>GrowLink Hourly Report</p>
            <div class="header-meta">
                <div class="meta-item">
                    <span class="meta-badge">Last Updated: {timestamp_str}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-badge">Status: {facility_status}</span>
                </div>
            </div>
        </div>

        <div class="status-bar">
            <div class="status-card {status_class}">
                <div>
                    <div class="status-card-label">Active Alerts</div>
                    <div class="status-card-value">{facility.get('activeAlerts', 0)}</div>
                </div>
            </div>
            <div class="status-card {modules_status}">
                <div>
                    <div class="status-card-label">Modules Online</div>
                    <div class="status-card-value">{facility.get('modulesOnline', 0)}/{facility.get('modulesOnline', 0) + facility.get('modulesOffline', 0)}</div>
                </div>
            </div>
            <div class="status-card good">
                <div>
                    <div class="status-card-label">System Efficiency</div>
                    <div class="status-card-value">{system_efficiency}</div>
                </div>
            </div>
            <div class="status-card good">
                <div>
                    <div class="status-card-label">Report Generated</div>
                    <div class="status-card-value">{report_time}</div>
                </div>
            </div>
        </div>

        {alerts_html}

        <div class="section-header">Room Status Dashboard</div>
        <div class="rooms-grid">
            {rooms_html}
        </div>

        {trends_html}

        {modules_html}

        <div class="footer">
            <p>CCGL GrowLink Analytics | Automated Cultivation Intelligence</p>
            <a href="https://portal2.growlink.com/rooms" class="footer-link">View Full Dashboard</a>
            <p style="margin-top: var(--spacing-lg);">Generated on {generation_time}</p>
        </div>
    </div>
</body>
</html>"""

    return html


def main():
    """Main execution."""
    print("CCGL GrowLink Hourly Report Generator")
    print("=" * 50)

    print("Loading data files...")
    state_data = load_json_file(STATE_FILE)
    hourly_data = load_json_file(HOURLY_FILE)
    logo_b64 = load_logo_base64()

    if not state_data:
        print("ERROR: Could not load state.json")
        return False

    if not logo_b64:
        print("WARNING: Could not load logo, using placeholder")
        logo_b64 = ""

    print(f"State data loaded: {len(state_data.keys())} sections")
    if hourly_data:
        print(f"Hourly data loaded: {len(hourly_data)} snapshots")

    print("Generating HTML report...")
    html_content = build_full_html(state_data, hourly_data, logo_b64)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(OUTPUT_FILE, 'w') as f:
            f.write(html_content)
        print(f"Report written to: {OUTPUT_FILE}")
    except Exception as e:
        print(f"ERROR writing report: {e}")
        return False

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_file = ARCHIVE_DIR / f"CCGL-Report-{timestamp}.html"
    try:
        with open(archive_file, 'w') as f:
            f.write(html_content)
        print(f"Archived report to: {archive_file}")
    except Exception as e:
        print(f"WARNING: Could not archive report: {e}")

    print("=" * 50)
    print("Report generation complete!")
    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
