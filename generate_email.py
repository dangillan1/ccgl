#!/usr/bin/env python3
"""
CCGL Daily Email Summary Generator
Generates a high-end HTML email from state.json + events.json data.
Designed for Gmail rendering with inline styles and table-based layout.
"""

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
STATE_PATH = BASE_DIR / "data" / "state.json"
EVENTS_PATH = BASE_DIR / "data" / "events.json"
DAILY_SUMMARY_PATH = BASE_DIR / "data" / "daily-summaries.json"
LOGO_PATH = BASE_DIR / "data" / "logo_base64.txt"
WORDMARK_PATH = BASE_DIR / "data" / "wordmark_base64.txt"
CONFIG_PATH = BASE_DIR / "data" / "config.json"
REPORT_URL = "https://dangillan1.github.io/ccgl/"
LOGO_URL = "https://dangillan1.github.io/ccgl/logo.png"
WORDMARK_URL = "https://dangillan1.github.io/ccgl/wordmark.png"

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


def fmt_timestamp(iso_str, fmt="%I:%M %p"):
    """Format an ISO timestamp string to a readable time."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return dt.strftime(fmt)
    except:
        return ""


def fmt_date_range(iso_str):
    """Format an ISO timestamp to 'Apr 5, 9:22 PM' style."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except:
        return ""


def generate_email_html():
    state = load_json(STATE_PATH)
    events = load_json(EVENTS_PATH)
    daily_summaries = load_json(DAILY_SUMMARY_PATH)

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

    # Use hosted logo URLs (avoids base64 bloat in email)
    logo_uri = LOGO_URL
    wordmark_uri = WORDMARK_URL

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
        <td style="vertical-align:middle;text-align:right;white-space:nowrap;">
            <div style="font-size:11px;font-weight:600;color:{TEXT};line-height:1.2;">{date_str}</div>
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

    # ---- 24-HOUR ROOM PERFORMANCE LOOKBACK ----
    # Pull from daily-summaries.json for real 24h data (not hourly state.json snapshot)
    room_order = ["Flower 1", "Flower 2", "Mom"]
    room_colors = {"Flower 1": ORANGE, "Flower 2": LIME, "Mom": BLUE}
    key_sensors = {
        "Flower 1": ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit", "Substrate VWC"],
        "Flower 2": ["Ambient Temperature", "Ambient Humidity", "Vapor Pressure Deficit"],
        "Mom": ["Ambient Temperature", "Ambient Humidity", "Substrate VWC", "Vapor Pressure Deficit"],
    }

    # Build a merged 24h view: combine today + yesterday summaries, and fold in event peaks
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today_daily = daily_summaries.get(today_str, {})
    yesterday_daily = daily_summaries.get(yesterday_str, {})

    # Fallback: if no data for today/yesterday, use the two most recent available dates
    if not today_daily and not yesterday_daily and daily_summaries:
        sorted_dates = sorted(daily_summaries.keys(), reverse=True)
        today_str = sorted_dates[0]
        yesterday_str = sorted_dates[1] if len(sorted_dates) > 1 else sorted_dates[0]
        today_daily = daily_summaries.get(today_str, {})
        yesterday_daily = daily_summaries.get(yesterday_str, {})

    def merge_sensor(s1, s2):
        """Merge two sensor summary dicts (avg/min/max/count) into a combined view."""
        if not s1: return dict(s2) if s2 else {}
        if not s2: return dict(s1)
        c1, c2 = s1.get("count", 0), s2.get("count", 0)
        total = c1 + c2
        merged = {
            "min": min(s1.get("min", 999), s2.get("min", 999)),
            "max": max(s1.get("max", -999), s2.get("max", -999)),
            "count": total,
        }
        # Weighted average
        if total > 0 and s1.get("avg") is not None and s2.get("avg") is not None:
            merged["avg"] = (s1["avg"] * c1 + s2["avg"] * c2) / total
        elif s1.get("avg") is not None:
            merged["avg"] = s1["avg"]
        elif s2.get("avg") is not None:
            merged["avg"] = s2["avg"]
        return merged

    def merge_room_data(today_room, yesterday_room):
        """Merge today + yesterday 'all' data for a rolling 24h+ view."""
        t_all = today_room.get("all", {})
        y_all = yesterday_room.get("all", {})
        merged = {}
        all_sensors = set(list(t_all.keys()) + list(y_all.keys()))
        for sensor in all_sensors:
            merged[sensor] = merge_sensor(t_all.get(sensor, {}), y_all.get(sensor, {}))
        return merged

    def fold_in_event_peaks(merged_all, room_events, room_resolved):
        """Ensure event peak values are reflected in the merged data."""
        for evt in list(room_events) + list(room_resolved):
            sensor = evt.get("sensor", "")
            peak = evt.get("peak_value")
            if sensor and peak is not None and sensor in merged_all:
                s = merged_all[sensor]
                if "above" in evt.get("condition", ""):
                    if peak > s.get("max", -999):
                        s["max"] = peak
                elif "below" in evt.get("condition", ""):
                    if peak < s.get("min", 999):
                        s["min"] = peak
            # Also fold in hourly_values from events
            for hv in evt.get("hourly_values", []):
                val = hv.get("value")
                if sensor and val is not None and sensor in merged_all:
                    s = merged_all[sensor]
                    if val > s.get("max", -999):
                        s["max"] = val
                    if val < s.get("min", 999):
                        s["min"] = val

    # Determine date label (clean, human-readable)
    has_today = bool(today_daily)
    has_yesterday = bool(yesterday_daily)
    def fmt_short_date(d_str):
        try:
            return datetime.strptime(d_str, "%Y-%m-%d").strftime("%b %d").replace(" 0", " ")
        except:
            return d_str
    if has_today:
        summary_label = f"Last 24h · {fmt_short_date(today_str)}"
    else:
        summary_label = f"Last 24h · {fmt_short_date(yesterday_str)}"

    def range_quality(s_min, s_max, sensor_name):
        """Rate how tight the 24h range was."""
        if s_min is None or s_max is None:
            return "N/A", MUTED
        spread = abs(s_max - s_min)
        if "Temperature" in sensor_name:
            if spread <= 5: return "tight", GREEN
            elif spread <= 10: return "moderate", ORANGE
            return "wide swing", RED
        elif "Humidity" in sensor_name:
            if spread <= 8: return "tight", GREEN
            elif spread <= 15: return "moderate", ORANGE
            return "wide swing", RED
        elif "VPD" in sensor_name or "Deficit" in sensor_name:
            if spread <= 0.3: return "tight", GREEN
            elif spread <= 0.6: return "moderate", ORANGE
            return "wide swing", RED
        elif "VWC" in sensor_name:
            if spread <= 10: return "tight", GREEN
            elif spread <= 20: return "moderate", ORANGE
            return "wide swing", RED
        return "ok", TEXT2

    def build_room_assessment(room, day_data, night_data, all_data, r_events, r_resolved):
        """Build narrative assessment from actual daily summary + events."""
        issues = []
        wins = []

        # Count events
        active_critical = sum(1 for e in r_events if e.get("severity") == "critical")
        active_warning = sum(1 for e in r_events if e.get("severity") == "warning")
        resolved_count = len(r_resolved)

        # Analyze temperature
        temp_all = all_data.get("Ambient Temperature", {})
        if temp_all:
            t_min, t_max = temp_all.get("min"), temp_all.get("max")
            if t_min is not None and t_max is not None:
                spread = t_max - t_min
                if t_max > 85:
                    issues.append(f"temp peaked {t_max:.0f}°F")
                elif spread > 10:
                    issues.append(f"temp swung {spread:.0f}°F")
                elif spread <= 5:
                    wins.append("temp well-controlled")

        # Analyze humidity
        hum_all = all_data.get("Ambient Humidity", {})
        if hum_all:
            h_avg = hum_all.get("avg")
            h_max = hum_all.get("max")
            if h_avg and h_avg > 75:
                issues.append(f"humidity averaged {h_avg:.0f}%")
            elif h_max and h_max > 85:
                issues.append(f"humidity peaked {h_max:.0f}%")
            elif h_avg and h_max:
                spread = h_max - hum_all.get("min", h_avg)
                if spread <= 8:
                    wins.append("humidity held tight")

        # Analyze VPD
        vpd_all = all_data.get("Vapor Pressure Deficit", {})
        if vpd_all:
            v_avg, v_min, v_max = vpd_all.get("avg"), vpd_all.get("min"), vpd_all.get("max")
            if v_avg is not None:
                if v_avg < 0.5:
                    issues.append(f"VPD averaged just {v_avg:.2f} kPa")
                elif v_min is not None and v_max is not None:
                    spread = v_max - v_min
                    if spread > 0.8:
                        issues.append(f"VPD swung {spread:.1f} kPa")
                    elif spread <= 0.3:
                        wins.append("VPD consistent")

        # Factor in events
        if active_critical > 0:
            evt_labels = [e.get("label", "") for e in r_events if e.get("severity") == "critical"]
            issues.insert(0, f"{', '.join(evt_labels[:2])} active")
        if resolved_count > 0:
            evt_labels = [e.get("label", "") for e in r_resolved]
            issues.append(f"{', '.join(evt_labels[:2])} resolved")

        # Build summary
        if active_critical > 0:
            return f"Needs immediate attention — {', '.join(issues[:2])}", RED
        elif len(issues) >= 2:
            return f"Challenging 24h — {', '.join(issues[:2])}", ORANGE
        elif issues:
            return f"{', '.join(wins[:1]) + ' but ' if wins else ''}{issues[0]}", ORANGE
        elif wins:
            return f"Strong 24h — {', '.join(wins[:2])}", GREEN
        return "Stable conditions over the last 24 hours", GREEN

    # Collect events per room (active + resolved)
    room_active_events = {}
    room_resolved_events = {}
    for evt in active_events:
        room_active_events.setdefault(evt.get("room", ""), []).append(evt)
    for evt in resolved_events:
        room_resolved_events.setdefault(evt.get("room", ""), []).append(evt)

    html += f"""
<!-- 24-Hour Room Performance -->
<tr><td style="padding:24px 20px 8px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td><div style="font-size:11px;font-weight:700;color:{TEAL};text-transform:uppercase;letter-spacing:1.5px;">24-Hour Room Performance</div></td>
        <td style="text-align:right;"><div style="font-size:10px;color:{MUTED};">{summary_label}</div></td>
    </tr>
    </table>
</td></tr>"""

    for room in room_order:
        color = room_colors.get(room, TEAL)
        sensors = key_sensors.get(room, [])
        r_events = room_active_events.get(room, [])
        r_resolved = room_resolved_events.get(room, [])

        # Merge today + yesterday for rolling 24h+ view
        today_room = today_daily.get(room, {})
        yesterday_room = yesterday_daily.get(room, {})
        all_data = merge_room_data(today_room, yesterday_room)
        # Fold in event peak values (catches spikes between summary calculations)
        fold_in_event_peaks(all_data, r_events, r_resolved)
        # Day/night from today's summary (most recent cycle data)
        day_data = today_room.get("day", yesterday_room.get("day", {}))
        night_data = today_room.get("night", yesterday_room.get("night", {}))
        reading_count = all_data.get("Ambient Temperature", {}).get("count", 0)

        assessment_text, assessment_color = build_room_assessment(
            room, day_data, night_data, all_data, r_events, r_resolved
        )
        has_critical = any(e.get("severity") == "critical" for e in r_events)
        has_warning = any(e.get("severity") == "warning" for e in r_events)
        if has_critical:
            status_badge = ("⚠ CRITICAL", f"{RED}22", RED)
        elif has_warning:
            status_badge = ("⚠ ATTENTION", f"{ORANGE}22", ORANGE)
        else:
            status_badge = ("✓ ON TRACK", f"{GREEN}22", GREEN)

        html += f"""
<tr><td style="padding:6px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_DARK};border-radius:10px;border-top:3px solid {color};overflow:hidden;">
    <tr><td style="padding:16px 20px 12px;">
        <!-- Room header -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td>
                <div style="font-size:13px;font-weight:700;color:{WHITE};">{room}
                    <span style="font-size:10px;font-weight:400;color:{TEXT2};margin-left:8px;">{stages.get(room, '')}</span>
                </div>
            </td>
            <td style="text-align:right;white-space:nowrap;width:1%;">
                <span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:9px;font-weight:700;background:{status_badge[1]};color:{status_badge[2]};text-transform:uppercase;letter-spacing:0.5px;white-space:nowrap;">{status_badge[0]}</span>
            </td>
        </tr>
        </table>

        <!-- Day / Night comparison header -->
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px;">
        <tr>
            <td width="28%" style="padding:4px 0;font-size:9px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:0.5px;"></td>
            <td width="24%" style="padding:4px 0;font-size:9px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:0.5px;text-align:center;">24h Range</td>
            <td width="24%" style="padding:4px 0;font-size:9px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:0.5px;text-align:center;">Avg</td>
            <td width="24%" style="padding:4px 0;font-size:9px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:0.5px;text-align:right;">Range</td>
        </tr>"""

        for sensor in sensors:
            s_all = all_data.get(sensor, {})
            s_min = s_all.get("min")
            s_max = s_all.get("max")
            s_avg = s_all.get("avg")
            short_name = sensor.replace("Ambient ", "").replace("Vapor Pressure Deficit", "VPD").replace("Substrate ", "")

            # Build range string from real 24h data
            if s_min is not None and s_max is not None and s_min != s_max:
                range_str = f"{fmt_sensor(sensor, s_min)} – {fmt_sensor(sensor, s_max)}"
            elif s_min is not None:
                range_str = f"Held {fmt_sensor(sensor, s_min)}"
            else:
                range_str = "N/A"

            # Average
            avg_str = fmt_sensor(sensor, s_avg) if s_avg is not None else "—"

            # Quality
            quality, q_color = range_quality(s_min, s_max, sensor)

            html += f"""
        <tr>
            <td style="padding:5px 0;font-size:11px;font-weight:600;color:{TEXT2};">{short_name}</td>
            <td style="padding:5px 0;font-size:11px;font-weight:700;color:{WHITE};text-align:center;">{range_str}</td>
            <td style="padding:5px 0;font-size:11px;color:{TEXT2};text-align:center;">{avg_str}</td>
            <td style="padding:5px 0;text-align:right;">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{q_color};"></span>
                <span style="font-size:9px;color:{q_color};margin-left:3px;">{quality}</span>
            </td>
        </tr>"""

        html += """
        </table>"""

        # Day vs Night VPD comparison (the key consistency metric)
        vpd_day = day_data.get("Vapor Pressure Deficit", {})
        vpd_night = night_data.get("Vapor Pressure Deficit", {})
        vpd_all = all_data.get("Vapor Pressure Deficit", {})
        if vpd_all:
            v_min = vpd_all.get("min")
            v_max = vpd_all.get("max")
            v_avg = vpd_all.get("avg")
            day_avg = vpd_day.get("avg")
            night_avg = vpd_night.get("avg")

            # Build VPD narrative
            vpd_parts = []
            if v_min is not None and v_max is not None:
                spread = abs(v_max - v_min)
                if spread <= 0.3:
                    vpd_note = f"VPD held {v_min:.2f}–{v_max:.2f} kPa — excellent consistency"
                    vpd_c = GREEN
                elif spread <= 0.6:
                    vpd_note = f"VPD ranged {v_min:.2f}–{v_max:.2f} kPa"
                    if day_avg and night_avg:
                        vpd_note += f" (day avg {day_avg:.2f}, night avg {night_avg:.2f})"
                    vpd_c = TEAL
                else:
                    vpd_note = f"VPD swung {v_min:.2f}–{v_max:.2f} kPa ({spread:.1f} kPa spread)"
                    if day_avg and night_avg:
                        vpd_note += f" — day avg {day_avg:.2f}, night avg {night_avg:.2f}"
                    vpd_c = ORANGE if spread <= 1.0 else RED

                html += f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:8px;">
        <tr><td>
            <div style="font-size:10px;color:{vpd_c};padding:6px 10px;background:{vpd_c}11;border-radius:5px;border-left:3px solid {vpd_c};">
                {vpd_note}
            </div>
        </td></tr>
        </table>"""

        # Event summary for this room (active + recently resolved)
        total_events = len(r_events) + len(r_resolved)
        if total_events > 0:
            evt_items = []
            for evt in r_events:
                sev = evt.get("severity", "warning")
                s_c = severity_color(sev)
                dur = evt.get("hours_active", 0)
                peak = evt.get("peak_value")
                sensor = evt.get("sensor", "")
                peak_str = f" · peaked {fmt_sensor(sensor, peak)}" if peak else ""
                evt_items.append(
                    f'<span style="color:{s_c};font-weight:600;">{evt.get("label","")}</span>'
                    f' <span style="color:{MUTED};">{format_duration(dur)} active{peak_str}</span>'
                )
            for evt in r_resolved:
                peak = evt.get("peak_value")
                sensor = evt.get("sensor", "")
                peak_str = f" · peaked {fmt_sensor(sensor, peak)}" if peak else ""
                evt_items.append(
                    f'<span style="color:{GREEN};font-weight:600;">{evt.get("label","")} ✓</span>'
                    f' <span style="color:{MUTED};">resolved{peak_str}</span>'
                )

            html += f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;">"""
            for item in evt_items[:4]:
                html += f"""
        <tr><td style="padding:2px 0;font-size:10px;line-height:1.4;">
            {item}
        </td></tr>"""
            html += """
        </table>"""

        # Room assessment narrative
        html += f"""
        <div style="font-size:10px;color:{assessment_color};margin-top:8px;padding-top:8px;border-top:1px solid {BORDER};">
            {assessment_text}
        </div>
    </td></tr>
    </table>
</td></tr>"""

    # ---- EVENTS & ACTIONS (combined panel: active events + 24h data-driven actions) ----
    # Build unified action items: event cards first, then 24h-derived flags
    action_items = []

    # 1. Active events as action cards (sorted: critical first, then by duration)
    for evt in sorted(active_events, key=lambda e: (0 if e.get("severity") == "critical" else 1, -e.get("hours_active", 0))):
        sev = evt.get("severity", "warning")
        s_color = severity_color(sev)
        room = evt.get("room", "")
        label = evt.get("label", "")
        sensor = evt.get("sensor", "")
        hours = evt.get("hours_active", 0)
        peak = evt.get("peak_value")
        cur = evt.get("current_value")
        escalated = evt.get("escalated", False)
        evt_started = fmt_date_range(evt.get("started", ""))
        badge = "ESCALATED" if escalated else sev.upper()
        badge_bg = f"{RED}33" if escalated else f"{s_color}22"
        peak_str = f" · peaked {fmt_sensor(sensor, peak)}" if peak and peak != cur else ""

        action_items.append({
            "type": "event",
            "level": sev,
            "color": s_color,
            "badge": badge,
            "badge_bg": badge_bg,
            "title": f"{room} — {label}",
            "detail": f"Active {format_duration(hours)}, currently {fmt_sensor(sensor, cur)}{peak_str}",
            "since": f"Since {evt_started}" if evt_started else "",
        })

    # 2. 24h data-driven flags (only add if not already covered by an active event)
    data_flags = []
    for room in room_order:
        t_room = today_daily.get(room, {})
        y_room = yesterday_daily.get(room, {})
        r_all = merge_room_data(t_room, y_room)
        fold_in_event_peaks(r_all, room_active_events.get(room, []), room_resolved_events.get(room, []))

        # VPD inconsistency
        vpd = r_all.get("Vapor Pressure Deficit", {})
        if vpd.get("min") is not None and vpd.get("max") is not None:
            vpd_spread = vpd["max"] - vpd["min"]
            if vpd_spread > 1.0:
                data_flags.append({
                    "type": "flag",
                    "level": "warning",
                    "color": ORANGE,
                    "text": f"{room} VPD swung {vpd['min']:.2f}–{vpd['max']:.2f} kPa over 24h ({vpd_spread:.1f} kPa spread). Review dehumidifier and HVAC cycling.",
                })

        # Extreme humidity
        hum = r_all.get("Ambient Humidity", {})
        if hum.get("avg") and hum["avg"] > 80:
            data_flags.append({
                "type": "flag",
                "level": "warning",
                "color": ORANGE,
                "text": f"{room} humidity averaged {hum['avg']:.0f}% over 24h (peaked {hum.get('max', 0):.0f}%). Botrytis risk in flower.",
            })

        # Extreme temp swings
        temp = r_all.get("Ambient Temperature", {})
        if temp.get("min") is not None and temp.get("max") is not None:
            t_spread = temp["max"] - temp["min"]
            if t_spread > 15:
                data_flags.append({
                    "type": "flag",
                    "level": "warning",
                    "color": ORANGE,
                    "text": f"{room} temp ranged {temp['min']:.0f}–{temp['max']:.0f}°F ({t_spread:.0f}° swing). Check HVAC and ventilation.",
                })

    total_items = len(action_items) + len(data_flags)
    if total_items > 0:
        # Section header
        critical_count = sum(1 for a in action_items if a["level"] == "critical")
        header_color = RED if critical_count > 0 else ORANGE
        html += f"""
<!-- Events & Actions -->
<tr><td style="padding:24px 20px 8px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td><div style="font-size:11px;font-weight:700;color:{header_color};text-transform:uppercase;letter-spacing:1.5px;">Events & Actions ({total_items})</div></td>
        <td style="text-align:right;"><div style="font-size:10px;color:{MUTED};">Based on 24h performance</div></td>
    </tr>
    </table>
</td></tr>"""

        # Render active event cards
        for item in action_items:
            html += f"""
<tr><td style="padding:4px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_DARK};border-radius:8px;border-left:4px solid {item['color']};">
    <tr><td style="padding:12px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td>
                <span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:9px;font-weight:700;background:{item['badge_bg']};color:{item['color']};text-transform:uppercase;letter-spacing:0.5px;">{item['badge']}</span>
                <span style="font-size:12px;font-weight:600;color:{WHITE};margin-left:8px;">{item['title']}</span>
            </td>
        </tr>
        <tr>
            <td style="padding-top:4px;">
                <div style="font-size:11px;color:{TEXT};line-height:1.4;">{item['detail']}</div>
                <div style="font-size:9px;color:{MUTED};margin-top:2px;">{item['since']}</div>
            </td>
        </tr>
        </table>
    </td></tr>
    </table>
</td></tr>"""

        # Render 24h data-driven flags
        if data_flags:
            html += f"""
<tr><td style="padding:12px 20px 4px;">
    <div style="font-size:9px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:1px;">24h Performance Flags</div>
</td></tr>"""
            for i, flag in enumerate(data_flags[:4], 1):
                html += f"""
<tr><td style="padding:3px 20px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG_DARK};border-radius:8px;">
    <tr>
        <td width="36" style="padding:10px 0 10px 14px;vertical-align:top;">
            <div style="width:24px;height:24px;border-radius:50%;background:{flag['color']}22;text-align:center;line-height:24px;font-size:11px;font-weight:800;color:{flag['color']};">{i}</div>
        </td>
        <td style="padding:10px 14px;font-size:11px;color:{TEXT};line-height:1.5;">{flag['text']}</td>
    </tr>
    </table>
</td></tr>"""

    # ---- SYSTEM HEALTH ----
    offline_modules = state.get("offline_modules", [])
    html += f"""
<!-- System Health -->
<tr><td style="padding:24px 20px 8px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td><div style="font-size:11px;font-weight:700;color:{BLUE};text-transform:uppercase;letter-spacing:1.5px;">System Health</div></td>
        <td style="text-align:right;"><div style="font-size:10px;color:{MUTED};">{data_range_str}</div></td>
    </tr>
    </table>
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
<tr><td style="padding:28px 20px 36px;">
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


def send_email(subject, html):
    """Send email via Gmail SMTP to configured recipients."""
    config = load_json(CONFIG_PATH)
    smtp_user = config.get("smtp_user", "")
    smtp_pass = config.get("smtp_app_password", "")
    recipients = config.get("email_recipients", [])

    if not smtp_user or not smtp_pass:
        print("⚠ SMTP credentials missing in config.json — skipping send")
        return False
    if not recipients:
        print("⚠ No email_recipients in config.json — skipping send")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"CCGL GrowLink <{smtp_user}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())
        print(f"✅ Email sent to {len(recipients)} recipients: {', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"❌ SMTP send failed: {e}")
        return False


if __name__ == "__main__":
    import sys

    subject, html = generate_email_html()
    print(f"Subject: {subject}")
    print(f"HTML length: {len(html):,} bytes")

    # Save preview
    preview_path = BASE_DIR / "email-preview.html"
    with open(preview_path, "w") as f:
        f.write(html)
    print(f"Preview saved: {preview_path}")

    # Send unless --preview-only flag
    if "--preview-only" not in sys.argv:
        send_email(subject, html)
    else:
        print("Preview only — skipping send")
