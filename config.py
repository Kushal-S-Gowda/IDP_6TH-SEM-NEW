# FloodSense Pro — Configuration File
# All API keys, constants, and settings in one place

import os

# ─── API KEYS ───────────────────────────────────────────────
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENROUTE_API_KEY = os.getenv("OPENROUTE_API_KEY")

# ─── TWILIO SMS (Alert Command Center / drill dispatch) ─────
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_API_KEY_SID = os.getenv("TWILIO_API_KEY_SID")
TWILIO_API_KEY_SECRET = os.getenv("TWILIO_API_KEY_SECRET")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
TWILIO_ALERT_TO = os.getenv("TWILIO_ALERT_TO")

# ─── FLASK SETTINGS ─────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_key")
DEBUG = True

# ─── DATABASE ───────────────────────────────────────────────
DATABASE_URI = "sqlite:///database/floodsense.db"

# ─── RISK LEVEL SETTINGS ────────────────────────────────────
RISK_LEVELS = {
    0: {"label": "LOW",     "color": "green",  "weight": 0.5},
    1: {"label": "MEDIUM",  "color": "yellow", "weight": 1.5},
    2: {"label": "HIGH",    "color": "orange", "weight": 3.0},
    3: {"label": "EXTREME", "color": "red",    "weight": 4.0},
}

# ─── RESOURCE OPTIMIZATION WEIGHTS ──────────────────────────
MIN_RESOURCE_THRESHOLD = 1  # Minimum resources per HIGH+ zone
EXTREME_ZONE_ALLOCATION = 0.40  # 40% of resources to EXTREME zones
HIGH_ZONE_ALLOCATION = 0.30     # 30% to HIGH zones

# ─── MAP SETTINGS ───────────────────────────────────────────
INDIA_MAP_CENTER = [20.5937, 78.9629]
INDIA_MAP_ZOOM = 5
BENGALURU_COORDS = [12.9716, 77.5946]

# ─── SAFE ZONES DATABASE (BENGALURU) ────────────────────────
SAFE_ZONES_BENGALURU = [
    {"name": "Nandi Hills",             "lat": 13.3702, "lon": 77.6835, "elevation": 1478, "capacity": 10000},
    {"name": "Lalbagh Botanical Garden","lat": 12.9507, "lon": 77.5848, "elevation": 921,  "capacity": 5000},
    {"name": "Palace Grounds",          "lat": 13.0000, "lon": 77.5800, "elevation": 915,  "capacity": 8000},
    {"name": "NICE Grounds Bidadi",     "lat": 12.7980, "lon": 77.3940, "elevation": 850,  "capacity": 6000},
    {"name": "NIMHANS Convention Centre","lat": 12.9407,"lon": 77.5940, "elevation": 920,  "capacity": 4000},
    {"name": "St. John's Medical College","lat": 12.9456,"lon": 77.6188,"elevation": 918,  "capacity": 2000},
    {"name": "Manipal Hospital",        "lat": 12.9578, "lon": 77.6430, "elevation": 916,  "capacity": 1500},
    {"name": "BBMP Relief Camp 1",      "lat": 13.0200, "lon": 77.5500, "elevation": 930,  "capacity": 3000},
    {"name": "BBMP Relief Camp 2",      "lat": 12.9100, "lon": 77.6100, "elevation": 910,  "capacity": 3000},
    {"name": "BBMP Relief Camp 3",      "lat": 12.9800, "lon": 77.7200, "elevation": 905,  "capacity": 3000},
]

# ─── MONITORED ZONES (BENGALURU HIGH-RISK AREAS) ────────────
BENGALURU_ZONES = [
    {"name": "Bellandur",      "lat": 12.9261, "lon": 77.6760, "elevation": 887, "population": 45000, "river_proximity": 0.5, "flood_history": 0.9},
    {"name": "Marathahalli",   "lat": 12.9591, "lon": 77.6972, "elevation": 892, "population": 32000, "river_proximity": 1.2, "flood_history": 0.8},
    {"name": "HSR Layout",     "lat": 12.9116, "lon": 77.6389, "elevation": 895, "population": 28000, "river_proximity": 0.8, "flood_history": 0.7},
    {"name": "Whitefield",     "lat": 12.9698, "lon": 77.7499, "elevation": 910, "population": 55000, "river_proximity": 2.5, "flood_history": 0.4},
    {"name": "Koramangala",    "lat": 12.9279, "lon": 77.6271, "elevation": 900, "population": 38000, "river_proximity": 1.0, "flood_history": 0.6},
    {"name": "BTM Layout",     "lat": 12.9166, "lon": 77.6101, "elevation": 893, "population": 42000, "river_proximity": 0.7, "flood_history": 0.75},
    {"name": "Indiranagar",    "lat": 12.9719, "lon": 77.6412, "elevation": 918, "population": 25000, "river_proximity": 3.0, "flood_history": 0.3},
    {"name": "Hebbal",         "lat": 13.0358, "lon": 77.5970, "elevation": 905, "population": 30000, "river_proximity": 0.6, "flood_history": 0.65},
    {"name": "Yelahanka",      "lat": 13.1007, "lon": 77.5963, "elevation": 930, "population": 22000, "river_proximity": 2.0, "flood_history": 0.3},
    {"name": "Electronic City","lat": 12.8399, "lon": 77.6770, "elevation": 889, "population": 48000, "river_proximity": 1.5, "flood_history": 0.5},
]

# ─── UPDATE INTERVAL ─────────────────────────────────────────
WEATHER_UPDATE_INTERVAL = 1800  # seconds (30 minutes)