#!/usr/bin/env python3
"""
CCGL Daily Email Summary Generator
Generates a high-end HTML email from state.json + events.json data.
Designed for Gmail rendering with inline styles and table-based layout.
"""

import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
STATE_PATH = BASE_DIR / "data" / "state.json"
EVENTS_PATH = BASE_DIR / "data" / "events.json"
LOGO_PATH = BASE_DIR / "data" / "logo_base64.txt"
WORDMARK_PATH = BASE_DIR / "data" / "wordmark_base64.txt"
REPORT_URL = "https://dangillan1.github.io/ccgl/"

# Brand colors
BG_DARK = "#0a1628"
BG_CARD = "#0f1f35"
BG_CARD_INNER = "#071318"
BORDER = "#1a3050"
TEAL = "#4E9E8E"
LIME = "#8DC63F"
BLUE = "#4A90B5"
RED = "#e74c3c"
ORANGE = "#f39c12"
GREEN = "#2ecc71"
TEXT = "#d0d8e0"
TEXT2 = "#7a8fa3"
MUTED = "#5a7088"
WHITE = "#ffffff"


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_logo(path):
    try:
        with open(path) as f:
            raw = f.read().strip()
        if not raw.startswith('data:'):
            raw = f'data:image/png;base64,{raw}'
        return raw
    except FileNotFoundError:
        return ""


def severity_color(sev):
    return {"critical": RED, "warning": ORANGE, "info": BLUE}.get(sev, ORANGE)


def fmt_sensor(name, value):
    if value is None:
        return "N/A"
    if "Temperature" in name or "Temp" in name:
        return f"{value:.1f}°F"
    elif "Humidity" in name:
        return f"{value:.1f}%"
    elif "CO2" in name:
        return f"{int(value)} ppm"
    elif "VPD" in name or "Deficit" in name:
        return f"{value:.2f} kPa"
    elif "pH" in name:
        return f"{value:.2f}"
    elif "TDS" in name:
        return f"{int(value)} ppm"
    elif "EC" in name:
        return f"{value:.2f} dS/m"
    elif "VWC" in name:
        return f"{value:.1f}%"
    elif "Float" in name:
        return f"{value:.0f}%"
    return f"{value}"


def health_color(score):
    if score >= 90:
        return GREEN
    elif score >= 75:
        return ORANGE
    return RED


def format_duration(hours):
    if hours < 1:
        return f"{int(hours * 60)}m"
    elif hours < 24:
        return f"{hours:.0f}h"
    else:
        d = int(hours // 24)
        h = int(hours % 24)
        return f"{d}d {h}h" if h else f"{d}d"


def generate_email_html():
    state = load_json(STATE_PATH)
    events = load_json(EVENTS_PATH)

    now = datetime.now()
    updated = state.get("last_updated", now.isoformat())

    # Parse data
    fac = state.get("facility_health", {})
    mod_online = fac.get("modules_online", 23)
    mod_offline = fac.get("modules_offline", 5)
    mod_total = mod_online + mod_offline
    health_score = int(mod_online / mod_total * 100) if mod_total > 0 else 80
    h_color = health_color(health_score)

    stages = state.get("growth_stages", {})
    alerts = state.get("critical_alerts", {})
    rooms = state.get("current_readings", {}).get("rooms", {})
    active_events = events.get("active", [])
    resolved_events = events.get("resolved", [])

    # Sort events: critical first
    active_events.sort(key=lambda e: (0 if e.get("severity") == "critical" else 1))

    # Count by severity
    critical_count = sum(1 for e in active_events if e.get("severity") == "critical")
    warning_count = sum(1 for e in active_events if e.get("severity") == "warning")

    # Subject line — lead with most critical alert, not health %
    top_alert = ""
    if active_events:
        top = active_events[0]  # Already sorted critical-first
        top_alert = f"{top.get('room', '')} {top.get('label', '')} ({fmt_sensor(top.get('sensor', ''), top.get('current_value', 0))})"
    if critical_count > 0:
        subject = f"🔴 CCGL Daily — {top_alert}"
    elif warning_count > 0:
        subject = f"🟡 CCGL Daily — {top_alert}"
    else:
        subject = f"🟢 CCGL Daily — All Clear · {health_score}% Facility Health"

    # Date display
    try:
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        date_str = dt.strftime("%A, %B %d, %Y")
        time_str = dt.strftime("%I:%M %p")
    except:
        dt = now
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")

    # Data time range (readings have min/max from the hourly window)
    data_timestamp = state.get("current_readings", {}).get("timestamp", updated)
    try:
        data_dt = datetime.fromisoformat(data_timestamp.replace("Z", "+00:00"))
        data_range_str = f"Last hour ending {data_dt.strftime('%I:%M %p')}"
    except:
        data_range_str = f"As of {time_str}"

    # Load logos
    logo_uri = load_logo(LOGO_PATH)
    wordmark_uri = load_logo(WORDMARK_PATH)

    # ---- BUILD HTML ----
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>CCGL Daily Summary</title>
</head>
<body style="margin:0;padding:0;background-color:#050d18;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">

<!-- Preheader text (hidden, shows in inbox preview) -->
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">
    {top_alert} · {len(active_events)} active events · {', '.join(stages.values())}
</div>

<!-- Outer wrapper -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#050d18;">
<tr><td align="center" style="padding:12px 8px;">

<!-- Main container (600px max) -->
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:{BG_CARD};border-radius:16px;overflow:hidden;border:1px solid {BORDER};">

<!-- Brand Header -->
<tr><td style="background:{BG_CARD_INNER};padding:18px 20px;border-bottom:1px solid {BORDER};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td width="48" style="vertical-align:middle;">
            <img src="{logo_uri}" alt="CCGL" width="48" height="48" style="display:block;border-radius:12px;border:1px solid {BORDER};" />
        </td>
        <td style="vertical-align:middle;padding-left:14px;">
            <div style="font-size:10px;font-weight:700;color:{TEAL};text-transform:uppercase;letter-spacing:2px;line-height:1;">Cape Cod Grow Lab</div>
            <div style="font-size:18px;font-weight:700;color:{WHITE};letter-spacing:-0.3px;margin-top:3px;line-height:1.1;">Daily Grow Summary</div>
        </td>
        <td width="140" style="vertical-align:middle;text-align:right;">
            <div style="font-size:11px;color:{TEXT2};line-height:1.2;">{date_str}</div>
            <div style="font-size:10px;color:{MUTED};margin-top:3px;line-height:1;">{len(active_events)} active · {len(resolved_events)} resolved</div>
        </td>
    </tr>
    </table>
</td></tr>

<!-- Growth Stages Bar -->
<tr><td style="padding:0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>"""

    stage_colors = {"Flower 1": ORANGE, "Flower 2": LIME, "Mom": BLUE}
    stage_count = len(stages)
    for room, stage in stages.items():
        color = stage_colors.get(room, TEAL)
        html += f"""
        <td width="{100 // stage_count}%" style="background:{color}11;padding:10px 16px;border-bottom:2px solid {color};text-align:center;">
            <div style="font-size:10px;font-weight:700;color:{color};text-transform:uppercase;letter-spacing:0.5px;">{room}</div>
            <div style="font-size:11px;color:{TEXT2};margin-top:2px;">{stage}</div>
        </td>"""

    html += """
    </tr>
    </table>
</td></tr>"""

    # ---- ACTIVE EVENTS SECTION ----
    if active_events:
        html += f"""
<!-- Active Events -->
<tr><td style="padding:24px 20px 8px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td><div style="font-size:11px;font-weight:700;color:{ORANGE};text-transform:uppercase;letter-spacing:1.5px;">Active Events ({len(active_events)})</div></td>
    </tr>
    </table>
</td></tr>"""

        for evt in active_events:
            sev = evt.get("severity", "warning")
            s_color = severity_color(sev)
            escalated = evt.get("escalated", False)
            hours = evt.get("hours_active", 0)
            consec = evt.get("consecutive_hours", 1)
            cur = evt.get("current_value", 0)
            peak = evt.get("peak_value", cur)
            sensor = evt.get("sensor", "")
            badge = "ESCALATED" if escalated else sev.upper()
            badge_bg = f"{RED}33" if escalated else f"{s_color}22"

            html += f"""
<tr><td style="padding:6px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_DARK};border-radius:10px;border-left:4px solid {s_color};overflow:hidden;">
    <tr><td style="padding:16px 20px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td>
                <span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:9px;font-weight:700;background:{badge_bg};color:{s_color};text-transform:uppercase;letter-spacing:0.5px;">{badge}</span>
                <div style="font-size:14px;font-weight:600;color:{WHITE};margin-top:6px;">{evt.get('label', '')}</div>
                <div style="font-size:11px;color:{TEAL};margin-top:2px;">{evt.get('room', '')} · {evt.get('growth_stage', '')}</div>
            </td>
            <td width="100" style="text-align:right;vertical-align:top;">
                <div style="font-size:22px;font-weight:800;color:{s_color};">{fmt_sensor(sensor, cur)}</div>
                <div style="font-size:9px;color:{TEXT2};text-transform:uppercase;margin-top:2px;">Current</div>
            </td>
        </tr>
        </table>
        <!-- Event metrics row -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;">
        <tr>
            <td width="33%" style="text-align:center;padding:8px 4px;background:{BG_CARD};border-radius:6px;">
                <div style="font-size:13px;font-weight:700;color:{WHITE};">{fmt_sensor(sensor, peak)}</div>
                <div style="font-size:9px;color:{TEXT2};text-transform:uppercase;">Peak</div>
            </td>
            <td width="4"></td>
            <td width="33%" style="text-align:center;padding:8px 4px;background:{BG_CARD};border-radius:6px;">
                <div style="font-size:13px;font-weight:700;color:{WHITE};">{format_duration(hours)}</div>
                <div style="font-size:9px;color:{TEXT2};text-transform:uppercase;">Duration</div>
            </td>
            <td width="4"></td>
            <td width="33%" style="text-align:center;padding:8px 4px;background:{BG_CARD};border-radius:6px;">
                <div style="font-size:13px;font-weight:700;color:{WHITE};">{consec}h</div>
                <div style="font-size:9px;color:{TEXT2};text-transform:uppercase;">Consecutive</div>
            </td>
        </tr>
        </table>
    </td></tr>
    </table>
</td></tr>"""

    # ---- RESOLVED EVENTS ----
    if resolved_events:
        html += f"""
<tr><td style="padding:20px 20px 8px;">
    <div style="font-size:11px;font-weight:700;color:{GREEN};text-transform:uppercase;letter-spacing:1.5px;">Recently Resolved ({len(resolved_events)})</div>
</td></tr>"""

        for evt in resolved_events[:3]:
            html += f"""
<tr><td style="padding:4px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_DARK};border-radius:8px;border-left:3px solid {GREEN};opacity:0.8;">
    <tr><td style="padding:12px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td>
                <span style="display:inline-block;padding:2px 6px;border-radius:3px;font-size:8px;font-weight:700;background:{GREEN}22;color:{GREEN};text-transform:uppercase;">Resolved</span>
                <span style="font-size:12px;color:{WHITE};margin-left:8px;font-weight:600;">{evt.get('label', '')}</span>
                <span style="font-size:11px;color:{TEXT2};margin-left:4px;">· {evt.get('room', '')}</span>
            </td>
            <td width="80" style="text-align:right;">
                <div style="font-size:11px;color:{TEXT2};">{format_duration(evt.get('duration_hours', 0))}</div>
            </td>
        </tr>
        </table>
    </td></tr>
    </table>
</td></tr>"""

    # ---- ROOM SNAPSHOT ----
    room_order = ["Flower 1", "Flower 2", "Mom"]
    room_colors = {"Flower 1": ORANGE, "Flower 2": LIME, "Mom": BLUE}
    key_sensors = {
        "Flower 1": ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit", "Substrate VWC"],
        "Flower 2": ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit"],
        "Mom": ["Ambient Temperature", "Ambient Humidity", "Substrate VWC", "Vapor Pressure Deficit"],
    }

    html += f"""
<!-- Room Snapshot -->
<tr><td style="padding:24px 20px 8px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td><div style="font-size:11px;font-weight:700;color:{TEAL};text-transform:uppercase;letter-spacing:1.5px;">Room Snapshot</div></td>
        <td style="text-align:right;"><div style="font-size:10px;color:{MUTED};">{data_range_str}</div></td>
    </tr>
    </table>
</td></tr>"""

    for room in room_order:
        r_data = rooms.get(room, {})
        color = room_colors.get(room, TEAL)
        sensors = key_sensors.get(room, [])

        html += f"""
<tr><td style="padding:6px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_DARK};border-radius:10px;border-top:3px solid {color};overflow:hidden;">
    <tr><td style="padding:16px 20px;">
        <div style="font-size:13px;font-weight:700;color:{WHITE};margin-bottom:10px;">{room}
            <span style="font-size:10px;font-weight:400;color:{TEXT2};margin-left:8px;">{stages.get(room, '')}</span>
        </div>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>"""

        for i, sensor in enumerate(sensors):
            s_data = r_data.get(sensor, {})
            val = s_data.get("value") if isinstance(s_data, dict) else s_data
            short_name = sensor.replace("Ambient ", "").replace("Vapor Pressure Deficit", "VPD").replace("Substrate ", "")

            # Flag if this sensor has an alert
            val_color = WHITE
            if room == "Flower 1" and "Temperature" in sensor and val and val > 85:
                val_color = RED
            elif room == "Flower 1" and "Humidity" in sensor and val and val > 70:
                val_color = ORANGE
            elif "VWC" in sensor and val and val < 10:
                val_color = RED
            elif "VWC" in sensor and val and val < 15:
                val_color = ORANGE

            html += f"""
            <td width="{100 // len(sensors)}%" style="text-align:center;padding:6px 4px;">
                <div style="font-size:16px;font-weight:700;color:{val_color};">{fmt_sensor(sensor, val)}</div>
                <div style="font-size:9px;color:{TEXT2};text-transform:uppercase;margin-top:2px;">{short_name}</div>
            </td>"""

        html += """
        </tr>
        </table>
    </td></tr>
    </table>
</td></tr>"""

    # ---- PRIORITY ACTIONS ----
    # Build priorities from alerts
    priorities = []
    for key, alert in alerts.items():
        status = alert.get("status", "")
        if status == "CRITICAL":
            priorities.insert(0, {"text": alert.get("note", key), "level": "critical"})
        elif status == "WARNING":
            priorities.append({"text": alert.get("note", key), "level": "warning"})

    if priorities:
        html += f"""
<!-- Priority Actions -->
<tr><td style="padding:24px 20px 8px;">
    <div style="font-size:11px;font-weight:700;color:{RED};text-transform:uppercase;letter-spacing:1.5px;">Priority Actions</div>
</td></tr>"""

        for i, p in enumerate(priorities[:4], 1):
            p_color = RED if p["level"] == "critical" else ORANGE
            html += f"""
<tr><td style="padding:4px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_DARK};border-radius:8px;">
    <tr>
        <td width="36" style="padding:12px 0 12px 14px;vertical-align:top;">
            <div style="width:28px;height:28px;border-radius:50%;background:{p_color}22;text-align:center;line-height:28px;font-size:13px;font-weight:800;color:{p_color};">{i}</div>
        </td>
        <td style="padding:12px 16px;font-size:12px;color:{TEXT};line-height:1.5;">{p['text']}</td>
    </tr>
    </table>
</td></tr>"""

    # ---- SYSTEM HEALTH ----
    offline_modules = state.get("offline_modules", [])
    html += f"""
<!-- System Health -->
<tr><td style="padding:24px 20px 8px;">
    <div style="font-size:11px;font-weight:700;color:{BLUE};text-transform:uppercase;letter-spacing:1.5px;">System Health</div>
</td></tr>
<tr><td style="padding:6px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_DARK};border-radius:10px;">
    <tr>
        <td width="33%" style="text-align:center;padding:16px 8px;">
            <div style="font-size:24px;font-weight:700;color:{h_color};">{mod_online}</div>
            <div style="font-size:9px;color:{TEXT2};text-transform:uppercase;margin-top:2px;">Online</div>
        </td>
        <td width="33%" style="text-align:center;padding:16px 8px;border-left:1px solid {BORDER};border-right:1px solid {BORDER};">
            <div style="font-size:24px;font-weight:700;color:{ORANGE if mod_offline > 0 else GREEN};">{mod_offline}</div>
            <div style="font-size:9px;color:{TEXT2};text-transform:uppercase;margin-top:2px;">Offline</div>
        </td>
        <td width="33%" style="text-align:center;padding:16px 8px;">
            <div style="font-size:24px;font-weight:700;color:{h_color};">{health_score}%</div>
            <div style="font-size:9px;color:{TEXT2};text-transform:uppercase;margin-top:2px;">Uptime</div>
        </td>
    </tr>
    </table>
</td></tr>"""

    if offline_modules:
        modules_str = " · ".join(offline_modules[:5])
        html += f"""
<tr><td style="padding:4px 20px 0;">
    <div style="font-size:10px;color:{MUTED};padding:4px 0;">Offline: {modules_str}</div>
</td></tr>"""

    # ---- CTA BUTTON ----
    html += f"""
<!-- CTA Button -->
<tr><td style="padding:28px 20px 8px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
        <a href="{REPORT_URL}" target="_blank" style="display:inline-block;padding:14px 40px;background:linear-gradient(135deg,{TEAL},{LIME});color:{BG_DARK};font-size:13px;font-weight:700;text-decoration:none;border-radius:8px;text-transform:uppercase;letter-spacing:1px;">View Full Report →</a>
    </td></tr>
    </table>
</td></tr>

<!-- Footer with logo -->
<tr><td style="padding:24px 20px 28px;border-top:1px solid {BORDER};background:{BG_CARD_INNER};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td style="text-align:center;">
            <img src="{logo_uri}" alt="CCGL" width="32" height="32" style="display:inline-block;border-radius:8px;opacity:0.6;margin-bottom:8px;" />
            <div style="font-size:11px;font-weight:600;color:{TEAL};">Cape Cod Grow Lab</div>
            <div style="font-size:10px;color:{MUTED};margin-top:4px;">Mindfully Cultivated Cannabis · Brewster, MA</div>
            <div style="font-size:9px;color:{MUTED};margin-top:8px;">Automated daily summary · {data_range_str}</div>
        </td>
    </tr>
    </table>
</td></tr>

</table>
<!-- End main container -->

</td></tr>
</table>
<!-- End outer wrapper -->

</body>
</html>"""

    return subject, html


if __name__ == "__main__":
    subject, html = generate_email_html()
    print(f"Subject: {subject}")
    print(f"HTML length: {len(html):,} bytes")

    # Save preview
    preview_path = BASE_DIR / "email-preview.html"
    with open(preview_path, "w") as f:
        f.write(html)
    print(f"Preview saved: {preview_path}")
