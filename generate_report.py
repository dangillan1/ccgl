#!/usr/bin/env python3
"""
CCGL GrowLink Report Generator (v3 — Enhanced Template Edition)
Loads report_template.html, fills placeholders from state.json,
and generates the visually rich "Amazing" version of the report.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path


# --- Paths ---
BASE_DIR = Path(__file__).parent
TEMPLATE_PATH = BASE_DIR / "report_template.html"
STATE_PATH = BASE_DIR / "data" / "state.json"
LOGO_PATH = BASE_DIR / "data" / "logo_base64.txt"
WORDMARK_PATH = BASE_DIR / "data" / "wordmark_base64.txt"
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


# --- Helpers ---

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def load_text(path):
    with open(path, 'r') as f:
        raw = f.read().strip()
    if not raw.startswith('data:'):
        raw = f'data:image/png;base64,{raw}'
    return raw

def fmt(sensor_name, value):
    if "Temperature" in sensor_name: return f"{value:.1f}°F"
    elif "Humidity" in sensor_name: return f"{value:.1f}%"
    elif "CO2" in sensor_name: return f"{int(value)} ppm"
    elif "VPD" in sensor_name or "Deficit" in sensor_name: return f"{value:.2f} kPa"
    elif "pH" in sensor_name: return f"{value:.2f}"
    elif "TDS" in sensor_name: return f"{int(value)} ppm"
    elif "EC" in sensor_name: return f"{value:.2f} dS/m"
    elif "VWC" in sensor_name: return f"{value:.1f}%"
    elif "Float" in sensor_name: return f"{value:.0f}%"
    return f"{value:.2f}"

def status_color(value, lo, hi):
    if lo <= value <= hi: return C["good"]
    margin = (hi - lo) * 0.15
    if (lo - margin) <= value <= (hi + margin): return C["warning"]
    return C["critical"]

def status_class(value, lo, hi):
    if lo <= value <= hi: return "good"
    margin = (hi - lo) * 0.15
    if (lo - margin) <= value <= (hi + margin): return "warning"
    return "critical"

def health_score(room_data):
    if not room_data or "sensors" not in room_data: return 100
    g = w = cr = 0
    for sn, sd in room_data["sensors"].items():
        v, lo, hi = sd.get("value", 0), sd.get("min", 0), sd.get("max", 0)
        s = status_class(v, lo, hi)
        if s == "good": g += 1
        elif s == "warning": w += 1
        else: cr += 1
    total = g + w + cr
    if total == 0: return 100
    return max(0, 100 - (w * 15) - (cr * 25))

def trend_arrow(delta, pct):
    if abs(pct) < 1:
        return f'<span style="color:{C["muted"]}">→ Stable</span>'
    elif delta > 0:
        color = C["critical"] if pct > 10 else C["warning"] if pct > 5 else C["lime"]
        return f'<span style="color:{color}">↑ +{pct:.1f}%</span>'
    else:
        color = C["critical"] if abs(pct) > 10 else C["warning"] if abs(pct) > 5 else C["lime"]
        return f'<span style="color:{color}">↓ {pct:.1f}%</span>'


# --- Section Builders ---

def build_alerts(state):
    ca = state.get("critical_alerts", {})
    offline = state.get("offline_modules", [])
    tank = state.get("tank_sensors", {})
    html = '<div class="card-grid">\n'

    if "flower1_high_humidity" in ca:
        a = ca["flower1_high_humidity"]
        hum = a.get("current_humidity", 71.33)
        vpd = a.get("vpd", 0.97)
        html += f'''<div class="card alert-card warning">
    <div class="alert-header">
        <span class="alert-icon">⚠️</span>
        <span class="alert-title">Flower 1: Humidity Crisis — Bud Rot Risk Elevated</span>
        <span class="badge badge-warning">WARNING</span>
    </div>
    <div class="alert-metrics">
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['warning']}">{hum:.1f}%</div><div class="alert-metric-label">Current RH</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['good']}">45-55%</div><div class="alert-metric-label">Target RH</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['warning']}">{vpd:.2f}</div><div class="alert-metric-label">VPD (kPa)</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['good']}">1.0-1.5</div><div class="alert-metric-label">Target VPD</div></div>
    </div>
    <div class="alert-description">Flower 1 humidity is {hum - 55:.0f} percentage points above optimal ceiling. At Week 4 flower with dense bud sites forming, this creates a prime environment for Botrytis cinerea (bud rot). VPD at {vpd:.2f} kPa is below the 1.0 minimum — transpiration is suppressed, moisture pooling in the canopy.</div>
    <div class="alert-ai"><strong>🧠 AI Analysis:</strong> The 6h trend shows humidity dropped 24.9% from 96.2%, suggesting a dehumidification cycle kicked in but hasn't achieved target. The gap between current ({hum:.1f}%) and optimal (55%) requires approximately 30% more dehumidification capacity. Cross-referencing with substrate VWC — wet media is contributing to room humidity through evapotranspiration.</div>
    <div class="alert-action">🎯 <strong>Action:</strong> Increase dehumidifier runtime. Add supplemental exhaust during lights-on (7 AM - 7 PM). Position portable dehu at canopy height for maximum moisture capture.</div>
</div>\n'''

    if "mom_substrate_dry" in ca:
        a = ca["mom_substrate_dry"]
        vwc = a.get("current_vwc", 9.8)
        html += f'''<div class="card alert-card">
    <div class="alert-header">
        <span class="alert-icon">🚨</span>
        <span class="alert-title">Mother Room: Substrate Critically Dry — Irrigation Emergency</span>
        <span class="badge badge-critical">CRITICAL</span>
    </div>
    <div class="alert-metrics">
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['critical']}">{vwc:.1f}%</div><div class="alert-metric-label">Current VWC</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['good']}">30-65%</div><div class="alert-metric-label">Target VWC</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['warning']}">0.70</div><div class="alert-metric-label">EC (dS/m)</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['good']}">1.2-2.0</div><div class="alert-metric-label">Target EC</div></div>
    </div>
    <div class="alert-description">Mother room substrate at {vwc:.1f}% VWC — critically below the 30% minimum and approaching permanent wilt point (5-8%). EC at 0.70 dS/m is severely depleted, indicating nutrient starvation alongside dehydration.</div>
    <div class="alert-ai"><strong>🧠 AI Analysis:</strong> The 3h trend shows VWC spiked +216% from 3.1% → 9.8%, suggesting a partial watering event occurred but was insufficient. EC crashed 68% in 3h (2.19 → 0.70), consistent with a flush-through with low-EC water. The irrigation system may be delivering water but at inadequate volume.</div>
    <div class="alert-action">🎯 <strong>Action:</strong> Hand water all mothers to field capacity IMMEDIATELY. Inspect every emitter for clogs. Verify timer soak duration. Follow up with half-strength balanced nutrients once VWC stabilizes above 40%.</div>
</div>\n'''

    if tank.get("sensor1") == "broken":
        html += f'''<div class="card alert-card warning">
    <div class="alert-header">
        <span class="alert-icon">🔧</span>
        <span class="alert-title">Nutrient Tank: Both Level Sensors Non-Functional</span>
        <span class="badge badge-warning">HARDWARE</span>
    </div>
    <div class="alert-metrics">
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['critical']}">2/2</div><div class="alert-metric-label">Sensors Down</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['warning']}">{tank.get("current_float", 93):.0f}%</div><div class="alert-metric-label">Float Reading</div></div>
        <div class="alert-metric"><div class="alert-metric-value" style="color:{C['muted']}">±{tank.get("float_spread", 16)}</div><div class="alert-metric-label">Float Spread</div></div>
    </div>
    <div class="alert-description">Both nutrient tank level sensors broken. Float readings unreliable with ±{tank.get("float_spread", 16)} spread. Manual verification required.</div>
    <div class="alert-action">🎯 <strong>Action:</strong> Schedule tank sensor replacement. Use manual dip-stick measurements until repair.</div>
</div>\n'''

    if offline:
        html += f'''<div class="card alert-card info">
    <div class="alert-header">
        <span class="alert-icon">📡</span>
        <span class="alert-title">{len(offline)} Monitoring Modules Offline</span>
        <span class="badge badge-info">SYSTEM</span>
    </div>
    <div class="alert-description">Offline: <strong>{", ".join(offline)}</strong>. Most are in non-critical zones. Flower 2 PIC offline is notable with harvest 7 days out.</div>
    <div class="alert-action">🎯 <strong>Action:</strong> Verify F2 PIC is non-essential for harvest. Power-cycle accessible modules.</div>
</div>\n'''

    html += '</div>'
    return html


def build_room_cards(state):
    rooms = state.get("current_readings", {}).get("rooms", {})
    stages = state.get("growth_stages", {})
    room_order = ["Flower 1", "Flower 2", "Mom", "Cure Room", "Dry Room"]
    html = '<div class="card-grid">\n'

    for rn in room_order:
        if rn not in rooms: continue
        rd = rooms[rn]
        sensors = rd
        hs = health_score(rd)
        stage = stages.get(rn, "Active" if rn != "Dry Room" else "Idle")

        if hs >= 80: dot = f'style="background:{C["good"]}"'; fill_class = "health-fill-good"; h_color = C["good"]
        elif hs >= 50: dot = f'style="background:{C["warning"]}"'; fill_class = "health-fill-warning"; h_color = C["warning"]
        else: dot = f'style="background:{C["critical"]}"'; fill_class = "health-fill-critical"; h_color = C["critical"]

        metrics = ''
        for sn, sd in sensors.items():
            v = sd.get("value", 0)
            lo, hi = sd.get("min", 0), sd.get("max", 0)
            sc = status_class(v, lo, hi)
            scol = status_color(v, lo, hi)
            metrics += f'''<div class="metric-item status-{sc}">
    <div class="metric-value" style="color:{scol}">{fmt(sn, v)}</div>
    <div class="metric-label">{sn.replace("Ambient ", "").replace("Solution ", "").replace("Substrate ", "Sub ")}</div>
    <div class="metric-range">{lo:.1f} – {hi:.1f}</div>
</div>\n'''

        callout = ''
        if rn == "Flower 2":
            callout = f'<div class="callout callout-warning" style="margin-top:14px"><strong>⚠ Data Gap:</strong> No substrate sensors. Cannot monitor root zone EC, VWC, or temperature for pre-harvest flush.</div>'
        elif rn == "Mom":
            callout = f'<div class="callout callout-critical" style="margin-top:14px"><strong>🚨 Irrigation Alert:</strong> Substrate VWC at {sensors.get("Substrate VWC", {}).get("value", 9.8):.1f}% — critically dry. Hand water immediately.</div>'
        elif rn == "Dry Room":
            dry = state.get("dry_room", {})
            callout = f'<div class="callout callout-info" style="margin-top:14px"><strong>📋 Status:</strong> {dry.get("status", "idle").upper()} — Awaiting F2 harvest (~April 13). Currently {dry.get("current_temp", 65.3):.1f}°F / {dry.get("current_humidity", 64.5):.1f}% RH.</div>'

        html += f'''<div class="card">
    <h3><span class="card-status-dot" {dot}></span> {rn} <span class="growth-stage">{stage}</span></h3>
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
        <div class="health-bar" style="flex:1"><div class="health-bar-fill {fill_class}" style="width:{hs}%"></div></div>
        <span style="font-size:13px;font-weight:600;color:{h_color}">{hs}%</span>
    </div>
    <div class="metric-grid">{metrics}</div>
    {callout}
</div>\n'''

    html += '</div>'
    return html


def build_feed_section(state):
    feed = state.get("current_readings", {}).get("rooms", {}).get("Central Feed System", {})
    trends = state.get("trends", {}).get("Central Feed System", {})
    tank = state.get("tank_sensors", {})

    ph = feed.get("Solution pH", {}).get("value", 6.38)
    tds = feed.get("Solution TDS", {}).get("value", 868)
    temp = feed.get("Solution Temperature", {}).get("value", 57.85)
    flt = feed.get("Solution Float", {}).get("value", 93)

    ph_1h = trends.get("Solution pH", {}).get("1h", {})
    tds_1h = trends.get("Solution TDS", {}).get("1h", {})
    temp_1h = trends.get("Solution Temperature", {}).get("1h", {})
    flt_1h = trends.get("Solution Float", {}).get("1h", {})

    ph_color = C["good"] if 5.5 <= ph <= 6.5 else C["warning"]
    tds_color = C["good"] if 700 <= tds <= 1100 else C["warning"]
    temp_color = C["good"] if 55 <= temp <= 72 else C["warning"]

    # Get substrate data for cross-room comparison
    rooms = state.get("current_readings", {}).get("rooms", {})
    f1_ec = rooms.get("Flower 1", {}).get("Substrate EC", {}).get("value", 0)
    f1_vwc = rooms.get("Flower 1", {}).get("Substrate VWC", {}).get("value", 0)
    mom_ec = rooms.get("Mom", {}).get("Substrate EC", {}).get("value", 0)
    mom_vwc = rooms.get("Mom", {}).get("Substrate VWC", {}).get("value", 0)

    html = f'''<div class="feed-grid">
    <div class="feed-card">
        <div class="feed-value" style="color:{ph_color}">{ph:.2f}</div>
        <div class="feed-label">Solution pH</div>
        <div class="feed-range">Target: 5.5 – 6.5</div>
        <div class="feed-trend">1h: {trend_arrow(ph_1h.get("delta", 0), ph_1h.get("pct", 0))}</div>
    </div>
    <div class="feed-card">
        <div class="feed-value" style="color:{tds_color}">{tds}</div>
        <div class="feed-label">TDS (ppm)</div>
        <div class="feed-range">Target: 700 – 1100</div>
        <div class="feed-trend">1h: {trend_arrow(tds_1h.get("delta", 0), tds_1h.get("pct", 0))}</div>
    </div>
    <div class="feed-card">
        <div class="feed-value" style="color:{temp_color}">{temp:.1f}°F</div>
        <div class="feed-label">Solution Temp</div>
        <div class="feed-range">Target: 60 – 72°F</div>
        <div class="feed-trend">1h: {trend_arrow(temp_1h.get("delta", 0), temp_1h.get("pct", 0))}</div>
    </div>
    <div class="feed-card alert">
        <div class="feed-value" style="color:{C['critical']}">{flt:.0f}%</div>
        <div class="feed-label">Tank Float</div>
        <div class="feed-range">⚠ Sensors Broken</div>
        <div class="feed-trend">1h: {trend_arrow(flt_1h.get("delta", 0), flt_1h.get("pct", 0))}</div>
    </div>
</div>

<div class="card-grid">
    <div class="insight-card feed">
        <h4>🧪 Solution Chemistry Analysis</h4>
        <p><strong>pH Status:</strong> At {ph:.2f}, solution pH is {"within" if 5.5 <= ph <= 6.5 else "outside"} the optimal 5.5-6.5 range. {"Nutrient lockout risk is minimal." if 5.5 <= ph <= 6.5 else "Watch for nutrient lockout."}</p>
        <p><strong>TDS Context:</strong> At {tds} ppm, feed concentration is {"ideal" if 700 <= tds <= 1100 else "outside target"}. TDS moved {tds_1h.get("delta", 0):.0f} ppm in the last hour ({tds_1h.get("pct", 0):.1f}%).</p>
        <p><strong>Temperature:</strong> Solution at {temp:.1f}°F is {"optimal" if 60 <= temp <= 72 else "cool but acceptable"} — dissolved oxygen maximized below 68°F.</p>
    </div>
    <div class="insight-card" style="border-left-color:{C['warning']}">
        <h4>🔋 Tank & Delivery Status</h4>
        <p><strong>Sensor Status:</strong> Both level sensors broken. Float at {flt:.0f}% unreliable (±{tank.get("float_spread", 16)} spread).</p>
        <p><strong>Consumption:</strong> Cannot track automatically. Typical daily: 15-25 gallons. Verify manually.</p>
        <div class="callout callout-warning"><strong>Recommendation:</strong> Schedule sensor replacement. Implement twice-daily manual checks.</div>
    </div>
</div>

<div class="card">
    <h3>⚙ Fertigation Intelligence Deep Dive</h3>
    <div class="card-grid">
                <div class="insight-card" style="border-left-color:{C['cyan']}">
                    <h4>📊 Substrate Cross-Room Comparison</h4>
                    <div class="dive-metrics">
                        <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f1_ec:.2f}</div><div class="dive-metric-label">F1 EC (dS/m)</div></div>
                        <div class="dive-metric"><div class="dive-metric-val" style="color:{C['muted']}">N/A</div><div class="dive-metric-label">F2 EC</div></div>
                        <div class="dive-metric"><div class="dive-metric-val" style="color:{C['critical']}">{mom_ec:.2f}</div><div class="dive-metric-label">Mom EC (dS/m)</div></div>
                    </div>
                    <div class="dive-metrics">
                        <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f1_vwc:.1f}%</div><div class="dive-metric-label">F1 VWC</div></div>
                        <div class="dive-metric"><div class="dive-metric-val" style="color:{C['muted']}">N/A</div><div class="dive-metric-label">F2 VWC</div></div>
                        <div class="dive-metric"><div class="dive-metric-val" style="color:{C['critical']}">{mom_vwc:.1f}%</div><div class="dive-metric-label">Mom VWC</div></div>
                    </div>
                    <p style="font-size:12px;color:{C['text']};margin-top:8px">F1 root zone thriving. Mom in crisis — severe dehydration and nutrient depletion. F2 has no substrate monitoring.</p>
                </div>
                <div class="insight-card" style="border-left-color:{C['purple']}">
                    <h4>🔬 Nutrient Uptake Intelligence</h4>
                    <p><strong>F1 Feed-to-Runoff:</strong> Feed EC 0.08 vs substrate EC {f1_ec:.2f} — {int(f1_ec/0.08) if 0.08 > 0 else 0}x concentration factor indicating active uptake with salt buildup.</p>
                    <p><strong>Mom Feed-to-Runoff:</strong> Feed EC 0.08 vs substrate EC {mom_ec:.2f} — low ratio consistent with dry-down flushing nutrients.</p>
                    <div class="callout callout-teal"><strong>System Limitation:</strong> Injector dosing rates not available via GrowLink API.</div>
                </div>
    </div>
</div>'''

    return html


def build_day_night(state):
    trends = state.get("trends", {})
    rooms = state.get("current_readings", {}).get("rooms", {})
    hour = datetime.now().hour

    html = '<div class="dn-grid">\n'

    # Flower 1
    f1 = rooms.get("Flower 1", {})
    f1_t = trends.get("Flower 1", {})
    f1_lights = "☀️ Lights ON" if 7 <= hour < 19 else "🌙 Lights OFF"
    f1_period = "Day Cycle" if 7 <= hour < 19 else "Night Cycle"

    html += f'''<div class="dn-card alert-state">
    <h4>🌱 Flower 1 — {f1_period} {f1_lights}</h4>
    <div class="dn-row"><span class="dn-label">Temperature</span><span class="dn-value" style="color:{C['good']}">{f1.get("Ambient Temperature", {}).get("value", 0):.1f}°F</span></div>
    <div class="dn-row"><span class="dn-label">Humidity</span><span class="dn-value" style="color:{C['warning']}">{f1.get("Ambient Humidity", {}).get("value", 0):.1f}%</span></div>
    <div class="dn-row"><span class="dn-label">VPD</span><span class="dn-value" style="color:{C['warning']}">{f1.get("Vapor Pressure Deficit", {}).get("value", 0):.2f} kPa</span></div>
    <div class="dn-row"><span class="dn-label">CO2</span><span class="dn-value" style="color:{C['good']}">{f1.get("Ambient CO2", {}).get("value", 0):.0f} ppm</span></div>
    <div class="dn-row"><span class="dn-label">6h Temp Change</span><span class="dn-value">{trend_arrow(f1_t.get("Ambient Temperature", {}).get("6h", {}).get("delta", 0), f1_t.get("Ambient Temperature", {}).get("6h", {}).get("pct", 0))}</span></div>
    <div class="dn-row"><span class="dn-label">6h Humidity Change</span><span class="dn-value">{trend_arrow(f1_t.get("Ambient Humidity", {}).get("6h", {}).get("delta", 0), f1_t.get("Ambient Humidity", {}).get("6h", {}).get("pct", 0))}</span></div>
    <div class="dn-takeaway"><strong>Key Takeaway:</strong> Humidity is the primary concern. Dehumidification cycle working but hasn't reached target. Temperature differential between day/night needs monitoring — target ≤10°F swing for terpene preservation.</div>
</div>\n'''

    # Flower 2
    f2 = rooms.get("Flower 2", {})
    f2_t = trends.get("Flower 2", {})
    f2_lights = "☀️ Lights ON" if 6 <= hour < 18 else "🌙 Lights OFF"
    f2_period = "Day Cycle" if 6 <= hour < 18 else "Night Cycle"

    html += f'''<div class="dn-card">
    <h4>🌱 Flower 2 — {f2_period} {f2_lights}</h4>
    <div class="dn-row"><span class="dn-label">Temperature</span><span class="dn-value" style="color:{C['good']}">{f2.get("Ambient Temperature", {}).get("value", 0):.1f}°F</span></div>
    <div class="dn-row"><span class="dn-label">Humidity</span><span class="dn-value" style="color:{C['good']}">{f2.get("Ambient Humidity", {}).get("value", 0):.1f}%</span></div>
    <div class="dn-row"><span class="dn-label">VPD</span><span class="dn-value" style="color:{C['good']}">{f2.get("Vapor Pressure Deficit", {}).get("value", 0):.2f} kPa</span></div>
    <div class="dn-row"><span class="dn-label">CO2</span><span class="dn-value" style="color:{C['good']}">{f2.get("Ambient CO2", {}).get("value", 0):.0f} ppm</span></div>
    <div class="dn-row"><span class="dn-label">6h Temp Change</span><span class="dn-value">{trend_arrow(f2_t.get("Ambient Temperature", {}).get("6h", {}).get("delta", 0), f2_t.get("Ambient Temperature", {}).get("6h", {}).get("pct", 0))}</span></div>
    <div class="dn-row"><span class="dn-label">6h CO2 Change</span><span class="dn-value">{trend_arrow(f2_t.get("Ambient CO2", {}).get("6h", {}).get("delta", 0), f2_t.get("Ambient CO2", {}).get("6h", {}).get("pct", 0))}</span></div>
    <div class="dn-takeaway"><strong>Key Takeaway:</strong> Excellent condition for final week. VPD ideal for resin production. Maintain these conditions through harvest.</div>
</div>\n'''

    # Mom
    mom = rooms.get("Mom", {})
    mom_t = trends.get("Mom", {})
    mom_lights = "☀️ Lights ON" if 8 <= hour or hour < 2 else "🌙 Lights OFF"
    mom_period = "Day Cycle" if 8 <= hour or hour < 2 else "Night Cycle"

    html += f'''<div class="dn-card alert-state">
    <h4>🌿 Mom Room — {mom_period} {mom_lights}</h4>
    <div class="dn-row"><span class="dn-label">Temperature</span><span class="dn-value" style="color:{C['good']}">{mom.get("Ambient Temperature", {}).get("value", 0):.1f}°F</span></div>
    <div class="dn-row"><span class="dn-label">Humidity</span><span class="dn-value" style="color:{C['good']}">{mom.get("Ambient Humidity", {}).get("value", 0):.1f}%</span></div>
    <div class="dn-row"><span class="dn-label">VPD</span><span class="dn-value" style="color:{C['good']}">{mom.get("Vapor Pressure Deficit", {}).get("value", 0):.2f} kPa</span></div>
    <div class="dn-row"><span class="dn-label">6h Humidity Change</span><span class="dn-value">{trend_arrow(mom_t.get("Ambient Humidity", {}).get("6h", {}).get("delta", 0), mom_t.get("Ambient Humidity", {}).get("6h", {}).get("pct", 0))}</span></div>
    <div class="dn-takeaway"><strong>Key Takeaway:</strong> Environmental conditions are solid — the crisis is underground. Focus all attention on the irrigation emergency. Once VWC recovers above 40%, environmental numbers will maintain themselves.</div>
</div>\n'''

    # Cure Room
    cure = rooms.get("Cure Room", {})
    html += f'''<div class="dn-card">
    <h4>🏺 Cure Room — Passive Monitoring</h4>
    <div class="dn-row"><span class="dn-label">Temperature</span><span class="dn-value" style="color:{C['good']}">{cure.get("Ambient Temperature", {}).get("value", 0):.1f}°F</span></div>
    <div class="dn-row"><span class="dn-label">Humidity</span><span class="dn-value" style="color:{C['good']}">{cure.get("Ambient Humidity", {}).get("value", 0):.1f}%</span></div>
    <div class="dn-row"><span class="dn-label">Target Temp</span><span class="dn-value" style="color:{C['muted']}">58-68°F</span></div>
    <div class="dn-row"><span class="dn-label">Target RH</span><span class="dn-value" style="color:{C['muted']}">55-65%</span></div>
    <div class="dn-takeaway"><strong>Key Takeaway:</strong> Cure conditions excellent. Both temp and humidity within ideal range. No action needed.</div>
</div>\n'''

    html += '</div>'
    html += f'''
<div class="callout callout-teal" style="margin-top:20px">
    <strong>💡 Light Schedules:</strong> &nbsp; F1: 7:00 AM – 7:00 PM (12h) &nbsp;|&nbsp; F2: 6:00 AM – 6:00 PM (12h) &nbsp;|&nbsp; Mom: 8:00 AM – 1:30 AM (17.5h)
    <br><span style="font-size:11px;color:{C['muted']}">CO2 supplementation not active in Mom/Veg rooms. Don't flag CO2 drops during lights-off periods.</span>
</div>'''

    return html


def build_deep_dive(state):
    rooms = state.get("current_readings", {}).get("rooms", {})
    dry = state.get("dry_room", {})
    anomalies = state.get("anomalies", [])
    f1 = rooms.get("Flower 1", {})
    f2 = rooms.get("Flower 2", {})
    mom = rooms.get("Mom", {})
    cure = rooms.get("Cure Room", {})
    stages = state.get("growth_stages", {})

    html = ''

    # F1
    html += f'''<div class="dive-card f1">
    <h3>🌸 Flower 1 — {stages.get("Flower 1", "Week 4 Flower")} Deep Assessment</h3>
    <div class="dive-section">
        <div class="dive-section-title">Environmental Snapshot</div>
        <div class="dive-metrics">
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f1.get("Ambient Temperature", {}).get("value", 0):.1f}°F</div><div class="dive-metric-label">Temperature</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['warning']}">{f1.get("Ambient Humidity", {}).get("value", 0):.1f}%</div><div class="dive-metric-label">Humidity</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['warning']}">{f1.get("Vapor Pressure Deficit", {}).get("value", 0):.2f}</div><div class="dive-metric-label">VPD (kPa)</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f1.get("Ambient CO2", {}).get("value", 0):.0f}</div><div class="dive-metric-label">CO2 (ppm)</div></div>
        </div>
    </div>
    <div class="dive-section">
        <div class="dive-section-title">Root Zone Health</div>
        <div class="dive-metrics">
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f1.get("Substrate EC", {}).get("value", 0):.2f}</div><div class="dive-metric-label">EC (dS/m)</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f1.get("Substrate VWC", {}).get("value", 0):.1f}%</div><div class="dive-metric-label">VWC</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f1.get("Substrate Temperature", {}).get("value", 0):.1f}°F</div><div class="dive-metric-label">Root Temp</div></div>
        </div>
        <p style="margin-top:12px">Root zone thriving — EC at {f1.get("Substrate EC", {}).get("value", 0):.2f} dS/m within ideal range, VWC at {f1.get("Substrate VWC", {}).get("value", 0):.1f}% optimal. Issue is purely environmental air management.</p>
    </div>
    <div class="dive-section">
        <div class="dive-section-title">Recommended Actions</div>
        <ul class="dive-checklist">
            <li>🔴 <strong>URGENT:</strong> Increase dehu capacity — target 50-55% RH during lights-on</li>
            <li>🔴 <strong>URGENT:</strong> Add oscillating fans at canopy level to break boundary layer moisture</li>
            <li>🟡 Consider potassium silicate foliar (0.5-1g/L) for cuticle strength</li>
            <li>🟡 Begin PK boost at 20% over baseline for stretch finish and resin</li>
            <li>🟢 CO2 at {f1.get("Ambient CO2", {}).get("value", 0):.0f} ppm good — maintain current levels</li>
        </ul>
    </div>
</div>\n'''

    # F2
    html += f'''<div class="dive-card f2">
    <h3>🌿 Flower 2 — Pre-Harvest Analysis ({stages.get("Flower 2", "Late Flower")})</h3>
    <div class="dive-section">
        <div class="dive-section-title">Environmental Snapshot</div>
        <div class="dive-metrics">
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f2.get("Ambient Temperature", {}).get("value", 0):.1f}°F</div><div class="dive-metric-label">Temperature</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f2.get("Ambient Humidity", {}).get("value", 0):.1f}%</div><div class="dive-metric-label">Humidity</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f2.get("Vapor Pressure Deficit", {}).get("value", 0):.2f}</div><div class="dive-metric-label">VPD (kPa)</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{f2.get("Ambient CO2", {}).get("value", 0):.0f}</div><div class="dive-metric-label">CO2 (ppm)</div></div>
        </div>
        <div class="callout callout-good" style="margin-top:12px"><strong>✅ All Clear:</strong> Every environmental parameter within optimal range. VPD at {f2.get("Vapor Pressure Deficit", {}).get("value", 0):.2f} kPa ideal for resin production.</div>
    </div>
    <div class="dive-section">
        <div class="dive-section-title">⚠ Critical Blind Spot: No Substrate Sensors</div>
        <p>Cannot track root zone EC, VWC, or temperature for pre-harvest flush effectiveness.</p>
    </div>
    <div class="dive-section">
        <div class="dive-section-title">Pre-Harvest Countdown Checklist</div>
        <ul class="dive-checklist">
            <li>📋 <strong>Trichomes:</strong> Assess daily. Target 70-80% cloudy, 10-20% amber</li>
            <li>📋 <strong>Flush:</strong> Begin plain pH'd water if not already flushing</li>
            <li>📋 <strong>Dark Period:</strong> Plan 48-hour dark period 2 days before harvest</li>
            <li>📋 <strong>Dry Room:</strong> Pre-condition to 60°F / 60% RH (currently {dry.get("current_temp", 65.3):.1f}°F / {dry.get("current_humidity", 64.5):.1f}%)</li>
            <li>📋 <strong>Equipment:</strong> Hang racks, fans, dehu ready in Dry Room</li>
            <li>📋 <strong>Trim Crew:</strong> Confirm availability for 4+ hour wet trim</li>
        </ul>
    </div>
</div>\n'''

    # Mom
    html += f'''<div class="dive-card mom">
    <h3>🚨 Mother Room — Irrigation Emergency Assessment</h3>
    <div class="dive-section">
        <div class="dive-section-title">Substrate Crisis</div>
        <div class="dive-metrics">
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['critical']}">{mom.get("Substrate VWC", {}).get("value", 0):.1f}%</div><div class="dive-metric-label">VWC (Critical)</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['critical']}">{mom.get("Substrate EC", {}).get("value", 0):.2f}</div><div class="dive-metric-label">EC (dS/m)</div></div>
            <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{mom.get("Substrate Temperature", {}).get("value", 0):.1f}°F</div><div class="dive-metric-label">Root Temp</div></div>
        </div>
        <div class="callout callout-critical"><strong>Permanent Wilt Risk:</strong> If VWC drops below 5-8%, root damage becomes irreversible. Drought-stressed mothers produce weak clones, impacting next production cycle.</div>
    </div>
    <div class="dive-section">
        <div class="dive-section-title">Immediate Response Protocol</div>
        <ul class="dive-checklist">
            <li>🔴 <strong>NOW:</strong> Hand water all mothers to field capacity</li>
            <li>🔴 <strong>NOW:</strong> Check irrigation timer — verify schedule and runtime</li>
            <li>🔴 <strong>NOW:</strong> Inspect every emitter for clogs, mineral buildup</li>
            <li>🟡 <strong>24h:</strong> Monitor VWC recovery — should climb above 40%</li>
            <li>🟡 <strong>48h:</strong> If EC hasn't recovered above 1.2, apply nutrients at 50% strength</li>
            <li>🟢 <strong>72h:</strong> Resume normal feeding once VWC stabilizes in 30-65%</li>
        </ul>
    </div>
</div>\n'''

    # Facility
    html += f'''<div class="dive-card facility">
    <h3>🏭 Facility Operations Summary</h3>
    <div class="card-grid">
        <div class="insight-card dry">
            <h4>🌡 Dry Room Readiness</h4>
            <div class="dive-metrics">
                <div class="dive-metric"><div class="dive-metric-val" style="color:{C['blue']}">{dry.get("current_temp", 65.27):.1f}°F</div><div class="dive-metric-label">Current Temp</div></div>
                <div class="dive-metric"><div class="dive-metric-val" style="color:{C['blue']}">{dry.get("current_humidity", 64.5):.1f}%</div><div class="dive-metric-label">Current RH</div></div>
                <div class="dive-metric"><div class="dive-metric-val" style="color:{C['muted']}">60°F</div><div class="dive-metric-label">Target Temp</div></div>
                <div class="dive-metric"><div class="dive-metric-val" style="color:{C['muted']}">60%</div><div class="dive-metric-label">Target RH</div></div>
            </div>
            <p>Status: <strong>{dry.get("status", "idle").upper()}</strong>. F2 harvest ~April 13. Pre-condition 48h before harvest.</p>
        </div>
        <div class="insight-card cure">
            <h4>🏺 Cure Room Status</h4>
            <div class="dive-metrics">
                <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{cure.get("Ambient Temperature", {}).get("value", 0):.1f}°F</div><div class="dive-metric-label">Temperature</div></div>
                <div class="dive-metric"><div class="dive-metric-val" style="color:{C['good']}">{cure.get("Ambient Humidity", {}).get("value", 0):.1f}%</div><div class="dive-metric-label">Humidity</div></div>
            </div>
            <p>Within ideal cure range (58-68°F, 55-65% RH). Ready for F1 cure ~mid-May.</p>
        </div>
    </div>
</div>\n'''

    # Anomalies
    if anomalies:
        html += f'''<div class="card" style="border-left:4px solid {C['purple']}">
    <h3 style="color:{C['purple']}">🔍 Anomaly Detection Report</h3>
    <p style="font-size:12px;color:{C['text2']};margin-bottom:16px">Automated detection of readings deviating significantly from 24h average.</p>
    <div class="card-grid">\n'''
        for a in anomalies:
            dev = a.get("deviation_pct", 0)
            sev = C["critical"] if dev > 50 else C["warning"] if dev > 25 else C["lime"]
            html += f'''<div class="insight-card" style="border-left-color:{sev}">
    <h4 style="font-size:13px">{a.get("room", "")} — {a.get("sensor", "")}</h4>
    <div class="dive-metrics">
        <div class="dive-metric"><div class="dive-metric-val" style="color:{sev}">{a.get("current", 0):.2f}</div><div class="dive-metric-label">Current</div></div>
        <div class="dive-metric"><div class="dive-metric-val" style="color:{C['muted']}">{a.get("avg_24h", 0):.2f}</div><div class="dive-metric-label">24h Avg</div></div>
        <div class="dive-metric"><div class="dive-metric-val" style="color:{sev}">{dev:.1f}%</div><div class="dive-metric-label">Deviation</div></div>
    </div>
</div>\n'''
        html += '</div></div>\n'

    return html


def build_priorities(state):
    priorities = [
        {"level": "urgent", "tag": "URGENT", "title": "Hand Water Mother Room Immediately",
         "desc": "Substrate VWC at 9.8% — approaching permanent wilt point. Hand water to field capacity. Check irrigation timer and every emitter."},
        {"level": "urgent", "tag": "URGENT", "title": "Increase Flower 1 Dehumidification",
         "desc": "Humidity at 71.3% (target 45-55%) with VPD at 0.97 kPa. Deploy additional dehu capacity and increase exhaust fan runtime during lights-on."},
        {"level": "high", "tag": "HIGH", "title": "Pre-Condition Dry Room for F2 Harvest",
         "desc": "F2 harvest ~April 13. Dry Room needs to reach 60°F / 60% RH. Begin conditioning 48h before harvest."},
        {"level": "high", "tag": "HIGH", "title": "Begin F2 Trichome Monitoring",
         "desc": "Daily trichome assessment. Target 70-80% cloudy, 10-20% amber. Plan 48-hour dark period 2 days before chop."},
        {"level": "medium", "tag": "MEDIUM", "title": "Schedule Tank Sensor Replacement",
         "desc": "Both sensors broken. Float unreliable (±16 spread). Use manual dip-stick measurements twice daily."},
        {"level": "medium", "tag": "MEDIUM", "title": "Plan F2 Substrate Sensor Installation",
         "desc": "No substrate monitoring in F2. Install EC/VWC/temp sensors for next cycle to enable data-driven flush management."},
        {"level": "low", "tag": "LOW", "title": "Review Offline Module Status",
         "desc": "5 modules offline. Verify expected vs. unexpected outages. F2 PIC may be relevant for harvest operations."},
    ]

    html = ''
    for i, p in enumerate(priorities, 1):
        html += f'''<div class="priority-card priority-{p['level']}">
    <div class="priority-num">{i}</div>
    <div class="priority-content">
        <div class="priority-tag">{p['tag']}</div>
        <div class="priority-title">{p['title']}</div>
        <div class="priority-desc">{p['desc']}</div>
    </div>
</div>\n'''

    return html


def build_system_health(state):
    fac = state.get("facility_health", {})
    offline = state.get("offline_modules", [])
    online = fac.get("modules_online", 22)
    off = fac.get("modules_offline", 6)
    total = online + off
    pct = int(online / total * 100) if total > 0 else 0
    efficiency = fac.get("system_efficiency", "79%")
    pct_color = C["good"] if pct >= 85 else C["warning"] if pct >= 70 else C["critical"]

    html = f'''<div class="exec-grid">
    <div class="exec-card"><div class="exec-number">{online}/{total}</div><div class="exec-label">Modules Online</div></div>
    <div class="exec-card"><div class="exec-number" style="color:{C['warning']}">{off}</div><div class="exec-label">Modules Offline</div></div>
    <div class="exec-card"><div class="exec-number" style="color:{pct_color}">{pct}%</div><div class="exec-label">System Health</div></div>
    <div class="exec-card"><div class="exec-number" style="color:{C['blue']}">{efficiency}</div><div class="exec-label">Efficiency</div></div>
</div>

<div class="sys-grid">
    <div class="sys-card offline">
        <h4>📡 Offline Modules ({len(offline)})</h4>
        <ul class="module-list">\n'''

    for mod in offline:
        dot = C["warning"] if "Flower" in mod else C["muted"]
        html += f'            <li><span class="module-dot" style="background:{dot}"></span>{mod}</li>\n'

    html += f'''        </ul>
        <div class="callout callout-info" style="margin-top:12px"><strong>Assessment:</strong> Clone/Veg modules expected offline. F2 PIC warrants attention with harvest approaching.</div>
    </div>
    <div class="sys-card issues">
        <h4>⚙ Known Issues</h4>
        <ul class="module-list">
            <li><span class="module-dot" style="background:{C['critical']}"></span><strong>Tank Sensors:</strong> Both broken, readings unreliable</li>
            <li><span class="module-dot" style="background:{C['warning']}"></span><strong>F2 Substrate:</strong> No sensors installed</li>
            <li><span class="module-dot" style="background:{C['blue']}"></span><strong>Dry Room:</strong> Idle, awaiting F2 harvest</li>
            <li><span class="module-dot" style="background:{C['muted']}"></span><strong>API Limits:</strong> Injector dosing rates unavailable</li>
            <li><span class="module-dot" style="background:{C['muted']}"></span><strong>CO2:</strong> Not supplemented in Mom/Veg</li>
        </ul>
    </div>
    <div class="sys-card">
        <h4>📊 Data Quality</h4>
        <ul class="module-list">
            <li><span class="module-dot" style="background:{C['good']}"></span><strong>Flower 1:</strong> Full suite ✓</li>
            <li><span class="module-dot" style="background:{C['warning']}"></span><strong>Flower 2:</strong> Environmental only</li>
            <li><span class="module-dot" style="background:{C['good']}"></span><strong>Mom:</strong> Full suite ✓</li>
            <li><span class="module-dot" style="background:{C['good']}"></span><strong>Cure Room:</strong> Environmental ✓</li>
            <li><span class="module-dot" style="background:{C['good']}"></span><strong>Dry Room:</strong> Environmental ✓</li>
            <li><span class="module-dot" style="background:{C['warning']}"></span><strong>Central Feed:</strong> Chemistry ✓, tank levels unreliable</li>
        </ul>
    </div>
</div>'''

    return html


# --- Main ---

def main():
    print("Loading data...")
    state = load_json(STATE_PATH)
    logo = load_text(LOGO_PATH)
    wordmark = load_text(WORDMARK_PATH)

    print("Loading template...")
    with open(TEMPLATE_PATH, 'r') as f:
        template = f.read()

    # Parse timestamps
    last_updated = state.get("last_updated", "")
    try:
        dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        data_time = dt.strftime("%B %d, %Y · %I:%M %p")
    except:
        data_time = "Unknown"

    now = datetime.now()
    gen_time = now.strftime("%B %d, %Y · %I:%M %p")

    # Calculate facility health
    rooms = state.get("current_readings", {}).get("rooms", {})
    scores = [health_score(rooms[rn]) for rn in ["Flower 1", "Flower 2", "Mom", "Cure Room", "Dry Room"] if rn in rooms]
    overall = int(sum(scores) / len(scores)) if scores else 80
    h_color = C["good"] if overall >= 80 else C["warning"] if overall >= 60 else C["critical"]

    # Growth stages for header
    stages = state.get("growth_stages", {})
    header_stages = f"F1: {stages.get('Flower 1', 'Flower')} · F2: {stages.get('Flower 2', 'Late Flower')} · Mom: {stages.get('Mom', 'Vegetative')}"

    # Build replacements
    replacements = {
        "{{LOGO_DATA_URI}}": logo,
        "{{WORDMARK_DATA_URI}}": wordmark,
        "{{HEADER_GROWTH_STAGES}}": header_stages,
        "{{HEADER_TIMESTAMPS}}": f"Data as of {data_time} · Report generated {gen_time}",
        "{{FACILITY_HEALTH_SCORE}}": f'<span style="color:{h_color}">{overall}%</span>',
        "{{ALERTS_SECTION}}": build_alerts(state),
        "{{ROOMS_SECTION}}": build_room_cards(state),
        "{{FEED_SECTION}}": build_feed_section(state),
        "{{DAYNIGHT_SECTION}}": build_day_night(state),
        "{{DEEPDIVE_SECTION}}": build_deep_dive(state),
        "{{PRIORITIES_SECTION}}": build_priorities(state),
        "{{HEALTH_SECTION}}": build_system_health(state),
        "{{FOOTER_META}}": f"Generated by CCGL GrowLink Analyst · {gen_time}",
    }

    print(f"Filling {len(replacements)} placeholders...")
    html = template
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)

    # Check for unfilled placeholders
    import re
    unfilled = re.findall(r'\{\{[A-Z_]+\}\}', html)
    if unfilled:
        print(f"  ⚠ Unfilled placeholders: {unfilled}")
    else:
        print("  ✓ All placeholders filled")

    # Write output
    print(f"Writing report to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, 'w') as f:
        f.write(html)

    # Copy to index.html for GitHub Pages
    index_path = BASE_DIR / "index.html"
    shutil.copy2(OUTPUT_PATH, index_path)
    print(f"  GitHub Pages: {index_path}")

    # Archive copy
    ARCHIVE_DIR.mkdir(exist_ok=True)
    archive_name = f"CCGL-Report-{now.strftime('%Y-%m-%d-%H%M')}.html"
    archive_path = ARCHIVE_DIR / archive_name
    shutil.copy2(OUTPUT_PATH, archive_path)

    size = os.path.getsize(OUTPUT_PATH)
    print(f"\n✓ Report generated!")
    print(f"  Size: {size/1024:.1f} KB ({size:,} bytes)")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  GitHub Pages: {index_path}")
    print(f"  Archive: {archive_path}")


if __name__ == "__main__":
    main()
