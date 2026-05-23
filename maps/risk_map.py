# FloodSense Pro — Folium Risk Map Generator with Heatmap

import folium
from folium.plugins import HeatMap, MarkerCluster
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from api.weather import get_weather_for_zones
from ml.predict import predict_all_zones

RISK_COLORS = {
    "LOW":     "#28a745",
    "MEDIUM":  "#ffc107",
    "HIGH":    "#fd7e14",
    "EXTREME": "#dc3545"
}

RISK_ICONS = {
    "LOW":     "✅",
    "MEDIUM":  "⚠️",
    "HIGH":    "🟠",
    "EXTREME": "🔴"
}

def generate_risk_map():
    print("Generating live risk map with heatmap...")

    # Get live data
    zones_with_weather = get_weather_for_zones(config.BENGALURU_ZONES, config.OPENWEATHER_API_KEY)
    zones_with_risk    = predict_all_zones(zones_with_weather)

    # Base map
    m = folium.Map(
        location=config.BENGALURU_COORDS,
        zoom_start=11,
        tiles="CartoDB dark_matter"
    )

    # ── Layer Control ────────────────────────────────────────
    # We'll add multiple layers user can toggle

    # ── Layer 1: Heatmap ─────────────────────────────────────
    heatmap_data = []
    for zone in zones_with_risk:
        risk_class = zone.get("risk_class", 0)
        population = zone.get("population", 10000)

        # Weight = risk level × population density
        # Higher risk + more people = hotter on heatmap
        weight = (risk_class + 1) * (population / 10000)

        # Add multiple points around zone center
        # to create spread effect on heatmap
        import random
        random.seed(hash(zone["name"]))
        for _ in range(int(weight * 3)):
            lat_offset = random.uniform(-0.015, 0.015)
            lon_offset = random.uniform(-0.015, 0.015)
            heatmap_data.append([
                zone["lat"] + lat_offset,
                zone["lon"] + lon_offset,
                weight
            ])

    HeatMap(
        heatmap_data,
        min_opacity=0.3,
        max_zoom=13,
        radius=35,
        blur=25,
        gradient={
            0.0: "blue",
            0.3: "cyan",
            0.5: "lime",
            0.7: "yellow",
            0.85: "orange",
            1.0: "red"
        },
        name="🌡️ Risk Heatmap"
    ).add_to(m)

    # ── Layer 2: Zone Markers ────────────────────────────────
    zone_layer = folium.FeatureGroup(name="📍 Risk Zones", show=True)

    for zone in zones_with_risk:
        risk_label = zone.get("risk_label", "LOW")
        color      = RISK_COLORS.get(risk_label, "#28a745")
        icon_text  = RISK_ICONS.get(risk_label, "✅")

        # Outer glow ring for HIGH/EXTREME
        if risk_label in ["HIGH", "EXTREME"]:
            folium.CircleMarker(
                location=[zone["lat"], zone["lon"]],
                radius=28,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.15,
                weight=1,
            ).add_to(zone_layer)

        # Main marker
        folium.CircleMarker(
            location=[zone["lat"], zone["lon"]],
            radius=18,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            weight=3,
            popup=folium.Popup(
                f"""
                <div style="font-family:Arial; min-width:220px; padding:5px;">
                    <h4 style="color:{color}; margin:0 0 8px 0; font-size:1rem;">
                        {icon_text} {zone['name']}
                    </h4>
                    <table style="width:100%; font-size:0.82rem; border-collapse:collapse;">
                        <tr style="background:#f0f5fa;">
                            <td style="padding:4px 6px;"><b>Risk Level</b></td>
                            <td style="padding:4px 6px; color:{color}; font-weight:bold;">
                                {risk_label}</td>
                        </tr>
                        <tr>
                            <td style="padding:4px 6px;"><b>AI Confidence</b></td>
                            <td style="padding:4px 6px;">{zone.get('risk_score',0)}%</td>
                        </tr>
                        <tr style="background:#f0f5fa;">
                            <td style="padding:4px 6px;"><b>Population</b></td>
                            <td style="padding:4px 6px;">{zone.get('population',0):,}</td>
                        </tr>
                        <tr>
                            <td style="padding:4px 6px;"><b>Temperature</b></td>
                            <td style="padding:4px 6px;">{zone.get('temperature',0)}°C</td>
                        </tr>
                        <tr style="background:#f0f5fa;">
                            <td style="padding:4px 6px;"><b>Rainfall</b></td>
                            <td style="padding:4px 6px;">
                                {zone.get('rainfall_1h',0)} mm/hr</td>
                        </tr>
                        <tr>
                            <td style="padding:4px 6px;"><b>Humidity</b></td>
                            <td style="padding:4px 6px;">{zone.get('humidity',0)}%</td>
                        </tr>
                        <tr style="background:#f0f5fa;">
                            <td style="padding:4px 6px;"><b>Wind</b></td>
                            <td style="padding:4px 6px;">
                                {zone.get('wind_speed',0)} km/h</td>
                        </tr>
                        <tr>
                            <td style="padding:4px 6px;"><b>Action</b></td>
                            <td style="padding:4px 6px; color:#ff9800; font-size:0.75rem;">
                                {zone.get('action','')}</td>
                        </tr>
                    </table>
                </div>
                """,
                max_width=280
            ),
            tooltip=f"{zone['name']} — {risk_label} RISK | Pop: {zone.get('population',0):,}"
        ).add_to(zone_layer)

        # Zone name label
        folium.Marker(
            location=[zone["lat"], zone["lon"]],
            icon=folium.DivIcon(
                html=f"""<div style="
                    font-size:0.68rem; font-weight:700;
                    color:white; text-align:center;
                    text-shadow: 1px 1px 3px black;
                    margin-top:24px; white-space:nowrap;">
                    {zone['name']}
                </div>""",
                icon_size=(120, 20),
                icon_anchor=(60, 0)
            )
        ).add_to(zone_layer)

    zone_layer.add_to(m)

    # ── Layer 3: Safe Zones ──────────────────────────────────
    safe_layer = folium.FeatureGroup(name="🏔️ Safe Zones", show=True)

    for sz in config.SAFE_ZONES_BENGALURU:
        folium.Marker(
            location=[sz["lat"], sz["lon"]],
            icon=folium.DivIcon(
                html=f"""<div style="
                    background: rgba(40,167,69,0.92);
                    border: 2px solid #28a745;
                    border-radius: 6px;
                    padding: 3px 8px;
                    font-size: 0.65rem;
                    font-weight: 700;
                    color: white;
                    white-space: nowrap;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.4);">
                    🏔️ {sz['name']}
                </div>""",
                icon_size=(160, 25),
                icon_anchor=(80, 12)
            ),
            popup=folium.Popup(
                f"""
                <div style="font-family:Arial; padding:5px;">
                    <h4 style="color:#28a745; margin:0 0 6px 0;">
                        🏔️ Safe Zone
                    </h4>
                    <b style="font-size:0.9rem;">{sz['name']}</b><br><br>
                    <table style="font-size:0.82rem;">
                        <tr><td><b>Elevation</b></td>
                            <td style="padding-left:10px;">{sz['elevation']}m</td></tr>
                        <tr><td><b>Capacity</b></td>
                            <td style="padding-left:10px;">{sz['capacity']:,} people</td></tr>
                        <tr><td><b>Status</b></td>
                            <td style="padding-left:10px; color:#28a745;">
                                <b>OPEN</b></td></tr>
                    </table>
                </div>
                """,
                max_width=200
            ),
            tooltip=f"🏔️ Safe Zone: {sz['name']} | {sz['elevation']}m | {sz['capacity']:,} capacity"
        ).add_to(safe_layer)

    safe_layer.add_to(m)

    # ── Layer 4: Population Density Heatmap ──────────────────
    pop_layer = folium.FeatureGroup(name="👥 Population Density", show=False)

    pop_heat_data = []
    for zone in zones_with_risk:
        pop = zone.get("population", 10000)
        import random
        random.seed(hash(zone["name"] + "pop"))
        for _ in range(int(pop / 3000)):
            lat_off = random.uniform(-0.012, 0.012)
            lon_off = random.uniform(-0.012, 0.012)
            pop_heat_data.append([
                zone["lat"] + lat_off,
                zone["lon"] + lon_off,
                pop / 50000
            ])

    HeatMap(
        pop_heat_data,
        min_opacity=0.25,
        radius=30,
        blur=20,
        gradient={
            0.0: "white",
            0.4: "yellow",
            0.7: "orange",
            1.0: "purple"
        },
        name="👥 Population Density"
    ).add_to(pop_layer)

    pop_layer.add_to(m)

    # ── Layer Control Toggle ─────────────────────────────────
    folium.LayerControl(
        position="topright",
        collapsed=False
    ).add_to(m)

    # ── Title ────────────────────────────────────────────────
    title_html = """
    <div style="position:fixed; top:10px; left:50%;
                transform:translateX(-50%);
                z-index:1000;
                background:rgba(10,22,40,0.93);
                border:2px solid #1565c0;
                border-radius:12px;
                padding:10px 25px;
                text-align:center;
                box-shadow: 0 4px 15px rgba(0,0,0,0.5);">
        <span style="color:#4fc3f7; font-size:1.1rem; font-weight:900;">
            🌊 FloodSense Pro — Live Risk Map
        </span><br>
        <span style="color:#90caf9; font-size:0.72rem;">
            Bengaluru Zone Risk Assessment | Heatmap + Zone Markers | Real-Time Data
        </span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    # ── Legend ───────────────────────────────────────────────
    legend_html = """
    <div style="position:fixed; bottom:20px; right:10px;
                z-index:1000;
                background:rgba(10,22,40,0.93);
                border:1px solid #1565c0;
                border-radius:10px;
                padding:12px 16px;
                font-family:Arial;
                box-shadow: 0 4px 15px rgba(0,0,0,0.5);">
        <p style="color:#4fc3f7; font-weight:700;
                  margin:0 0 8px 0; font-size:0.85rem;">
            Risk Levels
        </p>
        <div style="color:white; font-size:0.78rem; line-height:2;">
            <span style="color:#dc3545; font-size:1rem;">●</span>
                EXTREME — Full emergency<br>
            <span style="color:#fd7e14; font-size:1rem;">●</span>
                HIGH — Begin evacuation<br>
            <span style="color:#ffc107; font-size:1rem;">●</span>
                MEDIUM — Pre-position<br>
            <span style="color:#28a745; font-size:1rem;">●</span>
                LOW — Monitor only<br>
            <span style="color:#28a745; font-size:0.8rem;">▪</span>
                Safe Zones
        </div>
        <hr style="border-color:#1565c0; margin:8px 0;">
        <p style="color:#4fc3f7; font-weight:700;
                  margin:0 0 4px 0; font-size:0.8rem;">
            Heatmap Scale
        </p>
        <div style="background: linear-gradient(90deg,
             blue, cyan, lime, yellow, orange, red);
             height:8px; border-radius:4px; width:140px;"></div>
        <div style="display:flex; justify-content:space-between;
             color:#90caf9; font-size:0.7rem; width:140px; margin-top:2px;">
            <span>Low Risk</span><span>High Risk</span>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # Save
    os.makedirs("static", exist_ok=True)
    map_path = "static/risk_map.html"
    m.save(map_path)
    print(f"  Map saved → {map_path}")
    return map_path


if __name__ == "__main__":
    path = generate_risk_map()
    print(f"✅ Heatmap map generated → {path}")