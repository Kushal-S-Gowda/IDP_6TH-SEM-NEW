# FloodSense Pro — Main Flask Application
# All routes for citizen and authority dashboards

from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import sys
from datetime import datetime
import requests

# Our modules
from api.weather import get_current_weather, get_forecast, get_weather_for_zones, get_all_zones_with_risk
from ml.predict import predict_risk_from_weather, predict_all_zones, predict_risk
from ml.explain import explain_zone, explain_prediction
from optimization.allocate import allocate_resources
from routing.evacuation import get_full_evacuation_plan, find_nearest_safe_zones
from database import init_db, log_alert, get_alert_history, \
                     get_alert_stats, log_zone_snapshot, \
                     get_zone_history, log_drill_start, \
                     log_drill_complete, get_drill_history
import config

app = Flask(__name__)
init_db()
app.secret_key = config.SECRET_KEY



# ─── HOME ─────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("home.html", active_page="home")



@app.route("/alert-center")
def alert_center():
    return render_template("alert_command_center.html", active_page="alert")

# ─── CITIZEN ROUTES ───────────────────────────────────────────

@app.route("/citizen")
def citizen_dashboard():
    return render_template("citizen/dashboard.html", active_page="citizen")



@app.route("/api/citizen/risk")

def get_citizen_risk():

    """

    Main API: Given a city name, return full risk assessment.

    Called by citizen dashboard when user searches a location.

    """

    city = request.args.get("city", "Bengaluru")



    # Step 1: Get live weather

    weather = get_current_weather(city, config.OPENWEATHER_API_KEY)

    if weather["status"] == "error":

        return jsonify({"status": "error", "message": weather["message"]})



    # Step 2: Find matching zone data (or use defaults)

    zone_data = get_zone_data_for_city(city, weather)



    # Step 3: Predict risk (pass coords + API key so forecast rainfall is real)

    zone_for_pred = {
        **zone_data,
        "name": weather.get("city", city),
        "lat":  weather["lat"],
        "lon":  weather["lon"],
    }

    prediction = predict_risk_from_weather(
        weather, zone_for_pred, api_key=config.OPENWEATHER_API_KEY
    )



    # Step 4: Get evacuation plan if HIGH or EXTREME

    evacuation_plan = None

    if prediction["risk_class"] >= 2:

        evacuation_plan = get_full_evacuation_plan(

            weather["lat"], weather["lon"], city

        )

        # Remove heavy geometry for JSON response

        if evacuation_plan and "primary_safe_zone" in evacuation_plan:

            evac_zone = evacuation_plan["primary_safe_zone"]

            evacuation_plan["primary_safe_zone"] = {

                k: v for k, v in evac_zone.items()

                if k != "route_geometry"

            }



    # Step 5: Get forecast

    forecast_data = get_forecast(weather["lat"], weather["lon"], config.OPENWEATHER_API_KEY)

    forecast_chart = build_forecast_chart(forecast_data)



    return jsonify({

        "status":          "success",

        "city":            weather["city"],

        "weather":         weather,

        "prediction":      prediction,

        "evacuation_plan": evacuation_plan,

        "forecast_chart":  forecast_chart,

        "emergency_contacts": {

            "NDRF":           "011-24363260",

            "State Disaster": "1070",

            "Ambulance":      "108",

            "Fire":           "101",

            "Police":         "100"

        }

    })



# ─── AUTHORITY ROUTES ─────────────────────────────────────────

@app.route("/authority")
def authority_dashboard():
    return render_template("authority/dashboard.html", active_page="authority")



@app.route("/api/authority/zones")

def get_all_zones():

    """

    Returns risk assessment for all Bengaluru zones.

    Used to populate the authority map and zone table.

    """

    # Get weather for all zones

    zones_with_weather = get_weather_for_zones(config.BENGALURU_ZONES, config.OPENWEATHER_API_KEY)



    # Predict risk for each zone

    zones_with_risk = predict_all_zones(zones_with_weather)



    # Build summary stats

    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "EXTREME": 0}

    for z in zones_with_risk:

        risk_counts[z["risk_label"]] += 1



    return jsonify({

        "status":      "success",

        "zones":       zones_with_risk,

        "risk_summary": risk_counts,

        "total_zones": len(zones_with_risk),

        "total_population_at_risk": sum(

            z["population"] for z in zones_with_risk

            if z["risk_class"] >= 2

        )

    })



@app.route("/api/authority/allocate", methods=["POST"])

def run_allocation():

    """

    Run resource optimization for current zone risks.

    Receives available resources from authority user input.

    """

    data = request.get_json()



    available_resources = {

        "ambulances":    int(data.get("ambulances",    45)),

        "boats":         int(data.get("boats",          8)),

        "camp_beds":     int(data.get("camp_beds",   1500)),

        "food_units":    int(data.get("food_units",  5000)),

        "medical_teams": int(data.get("medical_teams", 12)),

    }



    # Get current zone risks

    zones_with_weather = get_weather_for_zones(config.BENGALURU_ZONES, config.OPENWEATHER_API_KEY)

    zones_with_risk    = predict_all_zones(zones_with_weather)



    # Run optimization

    allocation, summary = allocate_resources(zones_with_risk, available_resources)



    return jsonify({

        "status":     "success",

        "allocation": allocation,

        "summary":    summary,

        "resources_available": available_resources

    })



@app.route("/api/authority/evacuation_route")

def get_evacuation_route_api():

    """Get evacuation route for a specific zone."""

    zone_name = request.args.get("zone", "Bellandur")

    lat = float(request.args.get("lat", 12.9261))

    lon = float(request.args.get("lon", 77.6760))



    plan = get_full_evacuation_plan(lat, lon, zone_name)



    # Remove heavy geometry data

    if plan and "primary_safe_zone" in plan:

        plan["primary_safe_zone"] = {

            k: v for k, v in plan["primary_safe_zone"].items()

            if k != "route_geometry"

        }



    return jsonify({"status": "success", "plan": plan})



# ─── MAP ROUTE ────────────────────────────────────────────────

@app.route("/map")

def risk_map():

    """Generate and serve the live Folium risk map."""

    from maps.risk_map import generate_risk_map

    map_path = generate_risk_map()

    return send_file(map_path)


@app.route("/api/logs/predictions")
def view_prediction_log():
    """
    Returns last N prediction records from the CSV log.
    Professor can see: timestamp, zone, rainfall, temp,
    humidity, risk label, confidence — all in one place.
    """
    import csv
    limit = int(request.args.get("limit", 50))
    log_path = "logs/prediction_log.csv"
 
    if not os.path.isfile(log_path):
        return jsonify({
            "status": "empty",
            "message": "No predictions logged yet. Run a zone check first.",
            "records": []
        })
 
    with open(log_path, "r", newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
 
    # Return most recent records first
    records = list(reversed(reader))[:limit]
    return jsonify({
        "status":  "success",
        "total":   len(reader),
        "showing": len(records),
        "records": records
    })


@app.route("/api/alerts/sms", methods=["POST"])
def send_sms_alert():
    """Send flood SMS for one zone (manual button or live alert)."""
    from api.twilio_alerts import send_zone_sms

    data = request.get_json(silent=True) or {}
    zone_name = data.get("zone", "Unknown Zone")
    risk = data.get("risk_label", "HIGH")
    drill = bool(data.get("drill", False))

    result = send_zone_sms(zone_name, risk, drill=drill)
    if result.get("status") == "success":
        try:
            log_alert(
                zone_name=zone_name,
                alert_type="SMS_FLOOD",
                message=result["sent"][0].get("sid", "sent"),
                severity=risk,
            )
        except Exception:
            pass
        return jsonify(result)
    return jsonify(result), 400 if "not configured" in result.get("message", "").lower() else 500


@app.route("/api/alerts/sms/drill", methods=["POST"])
def send_drill_sms_alerts():
    """
    Batch SMS for Alert Command Center drill dispatch.
    Sends one message per triggered zone via Twilio.
    """
    from api.twilio_alerts import send_drill_flood_alerts

    data = request.get_json(silent=True) or {}
    zones = data.get("zones") or []
    if not zones:
        return jsonify({
            "status": "error",
            "message": "No zones in request. Trigger a drill scenario first.",
        }), 400

    result = send_drill_flood_alerts(zones)
    if result.get("status") == "success":
        zone_names = ", ".join(
            z.get("zone") or z.get("name", "?") for z in zones
        )
        try:
            log_alert(
                zone_name=zone_names,
                alert_type="SMS_DRILL_DISPATCH",
                message=f"{result.get('message_count', 0)} SMS sent (drill)",
                severity="DRILL",
            )
        except Exception:
            pass
        return jsonify(result)
    return jsonify(result), 500


# ─── PDF REPORT ROUTE ─────────────────────────────────────────

@app.route("/api/authority/report")

def generate_report():
    """Generate and download PDF situation report."""
    from reports.generate_report import create_situation_report
 
    zones_with_weather = get_weather_for_zones(
        config.BENGALURU_ZONES, config.OPENWEATHER_API_KEY
    )
    zones_with_risk = predict_all_zones(zones_with_weather)
 
    # Normalize keys for PDF / downstream (OWM uses rain_1h, temp)
    for z in zones_with_risk:
        r1 = z.get("rain_1h", z.get("rainfall_1h", 0))
        z["rainfall_1h"] = r1
        z["rainfall"] = r1
        z["temperature"] = z.get("temp", z.get("temperature", 0))
        z["rainfall_24h"] = z.get(
            "rainfall_24h", round(float(r1 or 0) * 8, 1)
        )
 
    pdf_path = create_situation_report(zones_with_risk)
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name="FloodSense_Situation_Report.pdf"
    )
 
# ─── HELPER FUNCTIONS ─────────────────────────────────────────

def get_zone_data_for_city(city, weather):

    """Match searched city to zone data or return defaults."""

    city_lower = city.lower()

    for zone in config.BENGALURU_ZONES:

        if zone["name"].lower() in city_lower or city_lower in zone["name"].lower():

            return zone

    # Default zone data for cities not in our database

    return {

        "elevation":      300,

        "river_proximity": 5,

        "flood_history":   0.3,

        "population":     50000

    }



def build_forecast_chart(forecast_data):

    """Build chart data for 48-hour rainfall forecast."""

    if forecast_data["status"] == "error":

        return {"labels": [], "rainfall": [], "risk_levels": []}



    labels   = []

    rainfall = []

    risk_levels = []



    for entry in forecast_data["forecast"][:16]:

        # Shorten datetime label

        dt = entry["time"]

        label = dt[5:16]  # "MM-DD HH:MM"

        labels.append(label)

        rainfall.append(entry["rain_3h"])



        # Simple risk color based on rainfall

        r = entry["rain_3h"]

        if r > 50:       risk_levels.append("red")

        elif r > 20:     risk_levels.append("orange")

        elif r > 5:      risk_levels.append("yellow")

        else:            risk_levels.append("green")



    return {

        "labels":      labels,

        "rainfall":    rainfall,

        "risk_levels": risk_levels

    }

# ─── SIMULATION ROUTE ────────────────────────────────────────

@app.route("/simulation")
def simulation_page():
    return render_template("flood_simulation.html", active_page="simulation")



@app.route("/api/simulate")

def simulate():

    """Run prediction with custom parameters for demo simulation."""

    rainfall_24h        = float(request.args.get("rainfall_24h", 5))

    rainfall_7d         = float(request.args.get("rainfall_7d", 20))

    temperature         = float(request.args.get("temperature", 28))

    humidity            = float(request.args.get("humidity", 60))

    wind_speed          = float(request.args.get("wind_speed", 10))

    elevation           = float(request.args.get("elevation", 900))

    river_proximity     = float(request.args.get("river_proximity", 5))

    flood_history_freq  = float(request.args.get("flood_history_freq", 0.7))

    soil_saturation_idx = float(request.args.get("soil_saturation_idx", 0.04))

    population_density  = float(request.args.get("population_density", 35000))



    prediction = predict_risk(

        rainfall_24h, rainfall_7d, temperature, humidity,

        wind_speed, elevation, river_proximity,

        flood_history_freq, soil_saturation_idx, population_density

    )

    return jsonify({"status": "success", "prediction": prediction})

@app.route("/trends")
def trends_page():
    return render_template("trends.html", active_page="trends")

# ─── RESCUE CAMP FINDER ───────────────────────────────────────

@app.route("/rescue")
def rescue_page():
    return render_template("rescue.html", active_page="rescue")



@app.route("/api/rescue/camps")

def get_rescue_camps():

    """

    Returns all safe zones ranked by distance, time,

    capacity and overall score from a given origin.

    """

    lat       = float(request.args.get("lat", 12.9261))

    lon       = float(request.args.get("lon", 77.6760))

    zone_name = request.args.get("zone", "Your Location")



    from geopy.distance import geodesic

    import openrouteservice



    client = openrouteservice.Client(key=config.OPENROUTE_API_KEY)



    camps = []
    for sz in config.SAFE_ZONES_BENGALURU:
        # PRIORITY: Try OpenRouteService first for real road routing
        try:
            coords = ((lon, lat), (sz["lon"], sz["lat"]))
            route = client.directions(
                        coords,
                        profile="driving-car",
                        radiuses=[1000, 1000]  # snap to nearest road within 1km
            )
            # Use real road distance and time from OpenRouteService
            dist_km = round(route["routes"][0]["summary"]["distance"] / 1000, 2)
            dur_min = round(route["routes"][0]["summary"]["duration"] / 60, 1)
            print(f"[RESCUE] OpenRouteService SUCCESS: {sz['name']} - {dist_km}km, {dur_min}min")
            
        except Exception as e:
            # RARE FALLBACK: Only use geopy when OpenRouteService completely fails
            print(f"[RESCUE] OpenRouteService FAILED for {sz['name']}: {e}")
            print(f"[RESCUE] Using geopy fallback for {sz['name']}")
            dist_km = round(geodesic((lat,lon),(sz["lat"],sz["lon"])).km, 2)
            dur_min = round(dist_km * 2.5, 1)  # Estimate: 2.5 min per km



        # Services based on name

        services = []

        name = sz["name"].lower()

        if any(x in name for x in ["medical","hospital","nimhans","john"]):

            services.extend(["medical","food"])

        else:

            services.extend(["shelter","food"])

        if "camp" in name or "palace" in name or "lalbagh" in name:

            services.append("boats")

        if "nandi" in name or "palace" in name or "manipal" in name:

            services.append("helicopter")

        if "medical" not in services and any(

            x in name for x in ["camp","palace","lalbagh","nimhans"]):

            services.append("medical")

        services = list(set(services))



        # Occupancy simulation

        import random

        random.seed(hash(sz["name"]) % 100)

        occupancy = random.randint(10, 55)



        # Overall score (0-100)

        # Lower distance = better, higher elevation = better,

        # lower occupancy = better, more services = better

        dist_score      = max(0, 100 - dist_km * 3)

        dur_score       = max(0, 100 - dur_min * 1.5)

        elev_score      = min(100, sz["elevation"] / 15)

        occupancy_score = 100 - occupancy

        service_score   = len(services) * 15

        capacity_score  = min(100, sz["capacity"] / 100)



        overall = round(

            dist_score * 0.30 +

            dur_score  * 0.25 +

            elev_score * 0.15 +

            occupancy_score * 0.15 +

            service_score   * 0.10 +

            capacity_score  * 0.05

        )



        camps.append({

            **sz,

            "road_distance_km":  dist_km,

            "road_duration_min": dur_min,

            "services":          services,

            "occupancy_pct":     occupancy,

            "overall_score":     min(99, overall),

            "description": get_camp_description(sz["name"])

        })



    # Sort by overall score

    camps.sort(key=lambda x: x["overall_score"], reverse=True)



    return jsonify({"status": "success", "camps": camps,

                    "origin": zone_name})



def get_camp_description(name):

    descriptions = {

        "Nandi Hills":

            "Highest safe point near Bengaluru. Primary evacuation destination for extreme floods.",

        "Lalbagh Botanical Garden":

            "Central Bengaluru relief hub. BBMP managed. Medical teams on standby.",

        "Palace Grounds":

            "Large open grounds. Helipad available. Army coordination point.",

        "NICE Grounds Bidadi":

            "South-west Bengaluru relief point. Accessible via NICE Road.",

        "NIMHANS Convention Centre":

            "BBMP designated shelter. Adjacent to NIMHANS hospital.",

        "St. John's Medical College":

            "Emergency medical facility. Priority for injured evacuees.",

        "Manipal Hospital":

            "Trauma and emergency care centre. Air ambulance helipad available.",

        "BBMP Relief Camp 1":

            "North Bengaluru BBMP camp. Rescue boats stationed for water rescue.",

        "BBMP Relief Camp 2":

            "South Bengaluru camp. Closest to Bellandur and HSR Layout zones.",

        "BBMP Relief Camp 3":

            "East Bengaluru camp. Closest to Whitefield and Marathahalli zones.",

    }

    return descriptions.get(name, "BBMP designated flood relief centre.")

# ═══════════════════════════════════════════════════════════════════

#  FIRE SIMULATION — ADD THIS ENTIRE BLOCK TO YOUR app.py

#  Paste it just BEFORE the line:  if __name__ == "__main__":

# ═══════════════════════════════════════════════════════════════════



# ── NEW IMPORT (add at top of app.py with other imports) ────────────

# import requests   ← you likely already have this


# ═══════════════════════════════════════════════════════════════════
#  FLOODSENSE PRO — MISSING EARLY WARNING ROUTES
#  Add these THREE things to your app.py:
#
#  1. The page route  →  /early-warning
#  2. API route       →  /api/early-warning/forecast
#  3. API route       →  /api/early-warning/signals
#
#  WHERE TO PASTE:
#  Open app.py, find the line:
#      @app.route("/fire-simulation")
#  Paste ALL of the code below JUST ABOVE that line.
# ═══════════════════════════════════════════════════════════════════


# ── 1. PAGE ROUTE ───────────────────────────────────────────────────
@app.route("/early-warning")
def early_warning_page():
    return render_template("early_warning.html", active_page="early_warning")


# ── 2. FORECAST API ─────────────────────────────────────────────────
@app.route("/api/early-warning/forecast")
def early_warning_forecast():
    """
    48h per-zone forecast + honest lead-time from OWM 3h slots (ml/early_warning_horizon.py).
    Displayed on /early-warning — Authority → Early Warning Command.
    """
    try:
        from ml.early_warning_horizon import build_early_warning_forecast

        zones_with_weather = get_weather_for_zones(
            config.BENGALURU_ZONES, config.OPENWEATHER_API_KEY
        )
        payload = build_early_warning_forecast(
            config.BENGALURU_ZONES,
            config.OPENWEATHER_API_KEY,
            zones_weather=zones_with_weather,
        )
        return jsonify(payload)
    except Exception as e:
        return jsonify({
            "status": "fallback",
            "message": str(e),
            "zones": [],
            "system_lead_time_hours": None,
        })


# ── 3. SIGNALS API ──────────────────────────────────────────────────
@app.route("/api/early-warning/signals")
def early_warning_signals():
    """
    Returns the 6 live signal values for the Early Warning gauges:
      rainfall_24h_mm, wind_speed_kmh, humidity_pct,
      lake_level_pct, drain_capacity_pct, soil_saturation_pct

    rainfall/wind/humidity come from OpenWeatherMap (real).
    lake_level, drain_capacity are estimated from rainfall + season
    (no real sensor network yet — honest approximation).
    Called by early_warning.html every 30 seconds.
    """
    import math

    try:
        # Single call for Bengaluru city-level conditions
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={config.BENGALURU_COORDS[0]}&lon={config.BENGALURU_COORDS[1]}"
            f"&appid={config.OPENWEATHER_API_KEY}&units=metric"
        )
        resp = requests.get(url, timeout=8)
        d    = resp.json()

        wind_kmh   = round(d.get("wind", {}).get("speed", 5) * 3.6, 1)
        humidity   = d.get("main", {}).get("humidity", 60)
        temp       = d.get("main", {}).get("temp", 28)
        rain_1h = d.get("rain", {}).get("1h", 0.0)
        # Use forecast-based 24h when available (same as ml/predict.py)
        from ml.predict import get_accumulated_rainfall
        _, rain_24h_fc, _ = get_accumulated_rainfall(
            config.BENGALURU_COORDS[0], config.BENGALURU_COORDS[1],
            config.OPENWEATHER_API_KEY,
        )
        rain_24h = round(rain_24h_fc, 1) if rain_24h_fc is not None else round(rain_1h * 8, 1)

        # Lake level: baseline 60%, rises with rainfall
        lake_level = round(min(99, 60 + rain_24h * 0.15 + (humidity - 50) * 0.05), 1)

        # Drain capacity: 100% when dry, drops as rain accumulates
        drain_cap  = round(max(5, 100 - rain_24h * 0.35 - (humidity - 40) * 0.1), 1)

        # Soil saturation: humidity + rain proxy
        soil_sat   = round(min(99, humidity * 0.6 + rain_24h * 0.2), 1)

        return jsonify({
            "status":              "live",
            "wind_speed_kmh":      wind_kmh,
            "humidity_pct":        humidity,
            "rainfall_24h_mm":     rain_24h,
            "lake_level_pct":      lake_level,
            "drain_capacity_pct":  drain_cap,
            "soil_saturation_pct": soil_sat,
            "temperature":         temp,
            "fetched_at":          datetime.now().strftime("%H:%M:%S"),
            "note": "rainfall/wind/humidity=live OWM · lake/drain/soil=estimated from live weather",
        })

    except Exception as e:
        # Fallback: safe defaults so the page doesn't break
        return jsonify({
            "status":              "fallback",
            "wind_speed_kmh":      11.0,
            "humidity_pct":        62,
            "rainfall_24h_mm":     5.0,
            "lake_level_pct":      68.0,
            "drain_capacity_pct":  82.0,
            "soil_saturation_pct": 45.0,
            "temperature":         29.0,
            "fetched_at":          datetime.now().strftime("%H:%M:%S"),
            "note":                f"Live API unavailable: {str(e)}",
        })

# ── ROUTE: Fire Simulation Page ─────────────────────────────────────

@app.route("/fire-simulation")
def fire_simulation():
    return render_template("fire_simulation.html", active_page="fire")





# ── API: Live fire conditions (feeds real wind/weather to the sim) ──

@app.route("/api/fire/conditions")

def get_fire_conditions():

    """

    Returns live weather conditions for the fire simulation.

    Pulls real wind speed & direction from OpenWeatherMap for Bengaluru.

    The JS simulation uses these as initial parameters.

    """

    import math



    try:

        # Reuse your existing weather API key

        url = (

            f"https://api.openweathermap.org/data/2.5/weather"

            f"?lat={config.BENGALURU_COORDS[0]}&lon={config.BENGALURU_COORDS[1]}"

            f"&appid={config.OPENWEATHER_API_KEY}&units=metric"

        )

        resp = requests.get(url, timeout=8)

        data = resp.json()



        wind_speed_ms  = data.get("wind", {}).get("speed", 5)       # m/s

        wind_speed_kmh = round(wind_speed_ms * 3.6, 1)

        wind_deg       = data.get("wind", {}).get("deg", 45)        # degrees

        humidity       = data.get("main", {}).get("humidity", 50)

        temp           = data.get("main", {}).get("temp", 28)

        weather_desc   = data.get("weather", [{}])[0].get("description", "clear sky")



        # Estimate fuel moisture from humidity + temperature

        # Dry + hot = low fuel moisture (dangerous), Humid = high (safer)

        fuel_moisture = round(max(5, min(40, humidity * 0.3 - temp * 0.2 + 15)), 1)



        # Fire danger rating (like FWI — simplified)

        danger_score = max(0, min(100, (100 - humidity) * 0.4 + wind_speed_kmh * 0.4 + (temp - 20) * 0.5))

        if danger_score >= 80:   fire_danger = "EXTREME"

        elif danger_score >= 60: fire_danger = "HIGH"

        elif danger_score >= 40: fire_danger = "MODERATE"

        else:                    fire_danger = "LOW"



        return jsonify({

            "status":        "live",

            "wind_speed_kmh": wind_speed_kmh,

            "wind_direction": wind_deg,

            "humidity":       humidity,

            "temperature":    temp,

            "fuel_moisture":  fuel_moisture,

            "weather_desc":   weather_desc,

            "fire_danger":    fire_danger,

            "danger_score":   round(danger_score, 1),

            "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

        })



    except Exception as e:

        # Fallback to simulated data if API fails

        return jsonify({

            "status":         "simulated",

            "wind_speed_kmh": 22,

            "wind_direction": 45,

            "humidity":       42,

            "temperature":    29,

            "fuel_moisture":  12,

            "weather_desc":   "partly cloudy",

            "fire_danger":    "MODERATE",

            "danger_score":   48.0,

            "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

            "note":           f"Live API unavailable: {str(e)}",

        })





# ── API: Fire economic impact calculator ────────────────────────────

@app.route("/api/fire/economic-impact", methods=["POST"])

def fire_economic_impact():

    """

    Given simulation results (cells burned, zone info),

    calculate detailed economic impact breakdown.

    This is what makes the simulation "financially aware" — your

    senior's advice about quantifying cost/benefit.

    """

    data         = request.get_json()

    burned_cells = int(data.get("burned_cells", 0))

    active_cells = int(data.get("active_cells", 0))

    zone_name    = data.get("zone_name", "Electronic City")

    sim_minutes  = int(data.get("sim_minutes", 60))

    wind_speed   = float(data.get("wind_speed", 20))



    # Property value per cell (₹ Crore) — realistic Bengaluru figures

    ZONE_VALUES = {

        "Electronic City": {"residential": 9,  "industrial": 18, "commercial": 14},

        "Whitefield":      {"residential": 11, "industrial": 20, "commercial": 16},

        "Koramangala":     {"residential": 14, "industrial": 12, "commercial": 18},

        "Marathahalli":    {"residential": 8,  "industrial": 14, "commercial": 11},

        "Hebbal":          {"residential": 7,  "industrial": 11, "commercial": 10},

        "Bannerghatta":    {"residential": 5,  "industrial": 6,  "commercial": 7},

    }

    vals = ZONE_VALUES.get(zone_name, {"residential": 8, "industrial": 12, "commercial": 10})

    avg_val = (vals["residential"] * 0.4 + vals["industrial"] * 0.4 + vals["commercial"] * 0.2)



    # Direct losses

    prop_loss       = round(burned_cells * avg_val * 0.65, 1)    # 65% destruction assumed

    infra_loss      = round(burned_cells * 1.8, 1)               # roads, utilities, telecom

    business_loss   = round(burned_cells * avg_val * 0.3 + sim_minutes * 0.5, 1)  # lost revenue

    relief_cost     = round((burned_cells + active_cells) * 0.12 + sim_minutes * 0.04, 1)

    total_direct    = round(prop_loss + infra_loss + business_loss + relief_cost, 1)



    # Indirect losses (multiplier effect)

    indirect_loss   = round(total_direct * 0.35, 1)              # supply chain, workforce

    total_economic  = round(total_direct + indirect_loss, 1)



    # Savings from early warning (our system's value proposition)

    # Research shows early warning reduces losses by 30-40%

    early_warning_saves = round(total_economic * 0.35, 1)

    optimised_response  = round(relief_cost * 0.22, 1)           # LP optimization savings

    total_saves         = round(early_warning_saves + optimised_response, 1)



    # ROI of FloodSense Pro Fire Module

    # System annual cost estimate: ~₹12 lakh

    system_cost_cr = 0.12

    roi_x          = round(total_saves / system_cost_cr, 0) if total_saves > 0 else 0



    # Structures at risk

    avg_structures_per_cell = 45

    structures_at_risk      = (burned_cells + active_cells) * avg_structures_per_cell

    people_displaced        = round(structures_at_risk * 4.2)   # avg household size



    return jsonify({

        "breakdown": {

            "property_loss_cr":    prop_loss,

            "infrastructure_cr":   infra_loss,

            "business_loss_cr":    business_loss,

            "relief_cost_cr":      relief_cost,

            "total_direct_cr":     total_direct,

            "indirect_loss_cr":    indirect_loss,

            "total_economic_cr":   total_economic,

        },

        "early_warning_impact": {

            "loss_prevented_cr":    early_warning_saves,

            "optimization_saves_cr": optimised_response,

            "total_saves_cr":       total_saves,

            "system_cost_cr":       system_cost_cr,

            "roi_multiplier":       roi_x,

        },

        "human_impact": {

            "structures_at_risk":   structures_at_risk,

            "people_displaced":     people_displaced,

            "area_burned_km2":      round(burned_cells * 0.04, 2),

        },

        "risk_rating": (

            "CATASTROPHIC" if total_economic > 500 else

            "MAJOR"        if total_economic > 100 else

            "SIGNIFICANT"  if total_economic > 20  else

            "MODERATE"

        )

    })





# ── API: Fire spread risk zones (which Bengaluru zones are in path) ─

@app.route("/api/fire/zone-threat")

def fire_zone_threat():

    """

    Given a fire origin and wind direction, predict which

    Bengaluru zones are in the downwind threat corridor.

    Integrates with existing BENGALURU_ZONES from config.

    """

    import math



    origin_x  = float(request.args.get("origin_x", 42))

    origin_y  = float(request.args.get("origin_y", 44))

    wind_dir  = float(request.args.get("wind_dir", 45))

    wind_spd  = float(request.args.get("wind_spd", 24))

    step      = int(request.args.get("step", 0))



    # Map zone names to approximate grid positions

    ZONE_GRID = {

        "Bellandur":      (36, 40), "Marathahalli":  (42, 30),

        "HSR Layout":     (28, 42), "Whitefield":    (46, 20),

        "Koramangala":    (28, 34), "BTM Layout":    (24, 40),

        "Indiranagar":    (32, 24), "Hebbal":        (22, 12),

        "Yelahanka":      (20, 8),  "Electronic City":(42, 48),

    }



    wind_rad     = math.radians(wind_dir)

    spread_dist  = step * 0.8   # cells per step at given wind speed factor

    wind_factor  = wind_spd / 20.0



    threatened = []

    for zone_name, (zx, zy) in ZONE_GRID.items():

        dx = zx - origin_x

        dy = zy - origin_y

        dist = math.sqrt(dx*dx + dy*dy)



        # Angle from origin to zone

        angle_to_zone = math.degrees(math.atan2(dy, dx)) % 360

        angle_diff    = abs(angle_to_zone - wind_dir) % 360

        if angle_diff > 180:

            angle_diff = 360 - angle_diff



        # Zone is threatened if:

        # 1. In the downwind cone (within 60° of wind direction)

        # 2. Close enough given current spread

        in_cone    = angle_diff < 60

        reachable  = dist < (spread_dist * wind_factor + 5)

        threat_pct = max(0, min(100, (1 - dist/40) * 100 * (1 if in_cone else 0.2)))



        if threat_pct > 5:

            threatened.append({

                "zone":       zone_name,

                "threat_pct": round(threat_pct, 0),

                "distance":   round(dist * 0.2, 1),  # convert to km

                "in_cone":    in_cone,

                "status": (

                    "BURNING"    if threat_pct > 80 else

                    "THREATENED" if threat_pct > 50 else

                    "AT RISK"    if threat_pct > 20 else

                    "MONITOR"

                )

            })



    threatened.sort(key=lambda x: x["threat_pct"], reverse=True)

    return jsonify({"zones": threatened, "total_threatened": len(threatened)})



# ─────────────────────────────────────────────────────────────────────────────

# This route powers the Alert Command Center page.

# It returns real per-zone weather + calculated risk for ALL zones.

# ─────────────────────────────────────────────────────────────────────────────



@app.route("/api/alert-center/all-zones")

def alert_center_all_zones():

    """

    Powers the Alert Command Center page.

    Called on page load and every 60 seconds for live refresh.



    What it does:

    - Calls OpenWeatherMap once per zone (16 zones = 16 API calls)

    - Combines real weather with hardcoded geography constants

    - Calculates flood risk score (XGBoost formula) per zone

    - Calculates Fire Weather Index (FWI) per zone

    - Returns season context banner data

    - Falls back gracefully to seasonal estimates if API fails



    Why per-zone calls matter:

    - Bengaluru spans 40km N-S — Yelahanka and Electronic City

      can have different rainfall during a localised storm event

    - Single-city call would give same rain to all zones — WRONG

    - Per-zone calls give honest, zone-specific readings

    """

    data = get_all_zones_with_risk(config.BENGALURU_ZONES, config.OPENWEATHER_API_KEY)

    return jsonify(data)

    # ═══════════════════════════════════════════════════════════════════
#  FLOODSENSE PRO — NEW ROUTES TO ADD TO app.py
#
#  STEP 1 — Add these imports at the TOP of app.py
#            (right after your existing imports block):
#
#    from database import init_db, log_alert, get_alert_history, \
#                         get_alert_stats, log_zone_snapshot, \
#                         get_zone_history, log_drill_start, \
#                         log_drill_complete, get_drill_history
#    from ml.explain import explain_zone, explain_prediction
#
#  STEP 2 — Add this ONE LINE right after app = Flask(__name__):
#
#    init_db()
#
#  STEP 3 — Paste all the routes below into app.py
#            (place them just above the  if __name__ == "__main__":  line)
#
# ═══════════════════════════════════════════════════════════════════


# ─── DATABASE: ALERT HISTORY API ─────────────────────────────────
@app.route("/api/db/alerts")
def api_alert_history():
    """Returns persisted alert history from SQLite."""
    limit = int(request.args.get("limit", 50))
    mode  = request.args.get("mode", None)     # optional: live / drill
    alerts = get_alert_history(limit=limit, mode=mode)
    stats  = get_alert_stats()
    return jsonify({"status": "success", "alerts": alerts, "stats": stats})


# ─── DATABASE: ZONE HISTORY API ──────────────────────────────────
@app.route("/api/db/zone-history")
def api_zone_history():
    """Returns risk history for a specific zone."""
    zone_name = request.args.get("zone", "Bellandur")
    limit     = int(request.args.get("limit", 48))
    history   = get_zone_history(zone_name, limit=limit)
    return jsonify({"status": "success", "zone": zone_name, "history": history})


# ─── DATABASE: DRILL LOG API ─────────────────────────────────────
@app.route("/api/db/drills")
def api_drill_history():
    """Returns persisted drill run history."""
    drills = get_drill_history(limit=20)
    return jsonify({"status": "success", "drills": drills})


@app.route("/api/db/drill-log", methods=["POST"])
def api_log_drill():
    """Called by the frontend when a drill starts/completes."""
    data   = request.get_json()
    action = data.get("action")   # "start" or "complete"

    if action == "start":
        drill_id = log_drill_start(
            scenario_name = data.get("scenario_name", "Unknown"),
            scenario_type = data.get("scenario_type", "natural"),
            lead_hours    = data.get("lead_hours", 0),
        )
        return jsonify({"status": "success", "drill_id": drill_id})

    elif action == "complete":
        log_drill_complete(
            drill_id      = data.get("drill_id"),
            zones_affected= data.get("zones_affected", 0),
            max_risk      = data.get("max_risk", "UNKNOWN"),
        )
        return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": "action must be start or complete"})


# ─── ML / HYDROLOGY (evaluator backend trace) ─────────────────────
@app.route("/api/ml/hydrology")
@app.route("/api/ml/hydrology/<zone_name>")
def api_ml_hydrology(zone_name=None):
    """
    Full equation-by-equation hydrology trace for one zone (ml/hydrology.py).
    Shows TWI, SCS-CN, HAND, FHI, Rational Q, Manning — not frontend UI.
    """
    from ml.hydrology import run_full_hydrology, AHP_WEIGHTS, ACTIVE_RAIN_24H_MM
    from ml.predict import predict_risk_from_weather, get_accumulated_rainfall

    zone_data = next(
        (z for z in config.BENGALURU_ZONES if z["name"].lower() == (zone_name or "").lower()),
        config.BENGALURU_ZONES[0],
    )
    zones_weather = get_weather_for_zones([zone_data], config.OPENWEATHER_API_KEY)
    weather = zones_weather[0] if zones_weather else {}
    prediction = predict_risk_from_weather(zone_data, zone_data, api_key=config.OPENWEATHER_API_KEY)

    trace = run_full_hydrology(
        float(prediction.get("rainfall_24h", 0)),
        float(prediction.get("rainfall_7d", 0)),
        float(zone_data.get("elevation", 920)),
        float(zone_data.get("river_proximity", 5)),
        float(zone_data.get("flood_history", 0.3)),
        float(zone_data.get("population", 30000)),
    )

    return jsonify({
        "status": "success",
        "zone": zone_data["name"],
        "data_source": prediction.get("data_source"),
        "log_note": "logs/prediction_log.csv is operational audit only — NOT training data",
        "training_data": "data/processed/flood_dataset.csv from ml/preprocess.py",
        "equations_module": "ml/hydrology.py",
        "ahp_weights": AHP_WEIGHTS,
        "active_rain_threshold_mm": ACTIVE_RAIN_24H_MM,
        "hydrology_trace": trace.to_dict(),
        "prediction": {
            k: prediction.get(k)
            for k in (
                "risk_label", "risk_class", "risk_score", "model_used", "fusion_method",
                "rainfall_6h", "rainfall_24h", "rainfall_7d", "fhi", "twi", "hand_m",
                "scs_runoff_mm", "cn_effective", "amc_class", "imd_24h_class",
                "rational_Q_m3s", "manning_drainage_index", "susceptibility_label",
            )
        },
        "literature": [
            "Beven & Kirkby (1979) TWI",
            "USDA TR-55 SCS-CN",
            "Nobre et al. (2011) HAND",
            "Mohammed et al. (2024) AHP urban FHI",
            "Springer Nat. Hazards (2025) AHP-ML hybrid",
        ],
    })


@app.route("/api/ml/equations")
def api_ml_equations():
    """Reference list of implemented formulas (for viva / paper appendix)."""
    return jsonify({
        "module": "ml/hydrology.py",
        "equations": [
            {"id": "TWI", "formula": "ln(a / tan(beta))", "reference": "Beven & Kirkby 1979"},
            {"id": "SCS-CN", "formula": "Q = (P - 0.2S)^2 / (P + 0.8S), S = 25400/CN - 254", "reference": "USDA TR-55"},
            {"id": "HAND", "formula": "(z - z_min) * (1 - exp(-1/d_river))", "reference": "HAND GIS literature"},
            {"id": "theta", "formula": "1 - exp(-P_7d / FC)", "reference": "Antecedent moisture proxy"},
            {"id": "FHI", "formula": "sum(w_i * f_i) * (1 + 0.25*Q/P)", "reference": "Mohammed et al. 2024 AHP"},
            {"id": "Rational", "formula": "Q_p = 0.278 * C * i * A", "reference": "Chow et al. 1988"},
            {"id": "Manning", "formula": "V = (1/n) * R^(2/3) * S^(1/2)", "reference": "Open-channel hydraulics"},
            {"id": "Ensemble", "formula": "rc = round(0.55*ML + 0.45*FHI_class)", "reference": "Hybrid AHP-ML 2025"},
        ],
        "features_ml": "16 (10 base + 6 engineered from hydrology)",
        "logs": "prediction_log.csv — inference audit only",
    })


# ─── XAI: EXPLAIN ZONE PREDICTION ────────────────────────────────
@app.route("/api/xai/explain")
def xai_explain():
    """
    Returns SHAP-based explanation for a zone's flood risk prediction.

    Query params:
      zone  — zone name (e.g. "Bellandur")
      OR pass individual feature values as query params for custom input.

    Returns feature contributions, top driver, and plain-English explanation.
    """
    zone_name = request.args.get("zone", None)

    if zone_name:
        # Find zone in config
        zone_data = next(
            (z for z in config.BENGALURU_ZONES if z["name"].lower() == zone_name.lower()),
            config.BENGALURU_ZONES[0]
        )
        # Get live weather for this zone
        zones_weather = get_weather_for_zones([zone_data], config.OPENWEATHER_API_KEY)
        weather = zones_weather[0] if zones_weather else {}
        result  = explain_zone(zone_data, weather)

    else:
        # Custom feature values from query params
        features = {
            "rainfall_24h":        float(request.args.get("rainfall_24h", 5)),
            "rainfall_7d":         float(request.args.get("rainfall_7d", 20)),
            "temperature":         float(request.args.get("temperature", 28)),
            "humidity":            float(request.args.get("humidity", 70)),
            "wind_speed":          float(request.args.get("wind_speed", 10)),
            "elevation":           float(request.args.get("elevation", 900)),
            "river_proximity":     float(request.args.get("river_proximity", 3)),
            "flood_history_freq":  float(request.args.get("flood_history_freq", 0.3)),
            "soil_saturation_idx": float(request.args.get("soil_saturation_idx", 0.1)),
            "population_density":  float(request.args.get("population_density", 20000)),
        }
        result = explain_prediction(features)

    return jsonify({"status": "success", "explanation": result})


# ─── XAI: EXPLAIN ALL ZONES ──────────────────────────────────────
@app.route("/api/xai/explain-all")
def xai_explain_all():
    """
    Returns XAI explanations for ALL 8 Bengaluru zones at once.
    Used by the authority dashboard XAI panel.
    """
    try:
        zones_weather = get_weather_for_zones(
            config.BENGALURU_ZONES, config.OPENWEATHER_API_KEY
        )
        explanations = []
        for i, zone in enumerate(config.BENGALURU_ZONES):
            weather = zones_weather[i] if i < len(zones_weather) else {}
            exp     = explain_zone(zone, weather)
            explanations.append(exp)

        return jsonify({
            "status":       "success",
            "explanations": explanations,
            "fetched_at":   datetime.now().strftime("%H:%M:%S"),
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ─── SIMULATION → EARLY WARNING PUSH ALERT ──────────────────────
@app.route("/api/simulation/push-alert", methods=["POST"])
def simulation_push_alert():
    """
    Receives alert payload from Fire or Flood Predictive Model simulations.
    Stores it so Early Warning Command can display it as a simulation-derived alert.
    Called when user clicks "Send Alert to Early Warning" in either simulation.

    This completes the loop:
      Simulation predicts scenario → Alert pushed → Early Warning Command notified
    """
    try:
        data = request.get_json(force=True) or {}

        source        = data.get("source", "simulation")           # fire_simulation / flood_simulation
        scenario      = data.get("scenario", "Unknown Scenario")
        sim_minutes   = data.get("sim_minutes", 0)
        high_risk     = data.get("high_risk_zones", [])
        econ_loss     = data.get("economic_loss_cr", "0 Cr")
        timestamp     = data.get("timestamp", datetime.now().isoformat())

        # Summarise for the alert log
        zone_names    = ", ".join(z.get("zone","?") for z in high_risk) if high_risk else "None"
        severity      = "CRITICAL" if len(high_risk) >= 3 else ("HIGH" if len(high_risk) >= 1 else "MONITOR")
        source_label  = "🔥 Fire Sim" if "fire" in source else "🌊 Flood Sim"

        # Log to the existing alert database
        try:
            log_alert(
                zone_name  = zone_names or "Simulation",
                alert_type = f"SIM_ALERT_{severity}",
                message    = f"{source_label}: Scenario '{scenario}' — T+{sim_minutes}min — "
                             f"Zones at risk: {zone_names} — Est. loss: {econ_loss}",
                severity   = severity
            )
        except Exception:
            pass  # DB logging optional — don't break the response

        return jsonify({
            "status":    "ok",
            "received":  scenario,
            "severity":  severity,
            "zones_flagged": len(high_risk),
            "message":   f"Alert from {source_label} logged. Early Warning Command updated.",
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ─── RUN ──────────────────────────────────────────────────────

if __name__ == "__main__":

    os.makedirs("database", exist_ok=True)

    print("\n" + "=" * 50)

    print("  FloodSense Pro — Starting Server")

    print("  Citizen Dashboard : http://127.0.0.1:5000/citizen")

    print("  Authority Dashboard: http://127.0.0.1:5000/authority")

    print("=" * 50 + "\n")

    app.run(debug=True, port=5000)