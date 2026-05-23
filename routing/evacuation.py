# FloodSense Pro — Evacuation Routing Module
# Finds nearest safe zone and calculates evacuation route

import math
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ORS_AVAILABLE = False
ORS_ERROR = None
client = None
try:
    import openrouteservice
    client = openrouteservice.Client(key=config.OPENROUTE_API_KEY)
    ORS_AVAILABLE = True
except Exception as e:
    ORS_AVAILABLE = False
    ORS_ERROR = str(e)


def _haversine_km(lat1, lon1, lat2, lon2):
    """Dependency-free great-circle distance."""
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2) + math.cos(p1) * math.cos(p2) * (math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c

def find_nearest_safe_zones(origin_lat, origin_lon, top_n=3):
    """
    Find nearest safe zones from a given location.
    Returns top_n closest safe zones sorted by distance.
    """
    distances = []

    for zone in config.SAFE_ZONES_BENGALURU:
        dist_km = _haversine_km(origin_lat, origin_lon, zone["lat"], zone["lon"])
        distances.append({**zone, "straight_distance_km": round(dist_km, 2)})

    # Sort by straight-line distance
    distances.sort(key=lambda x: x["straight_distance_km"])
    return distances[:top_n]


def get_evacuation_route(origin_lat, origin_lon, dest_lat, dest_lon):
    """
    Get road route between origin and destination.
    Returns distance, duration, and route geometry.
    """
    if not ORS_AVAILABLE:
        # Simple fallback: calculate straight-line distance and estimate time
        from geopy.distance import geodesic
        dist_km = geodesic((origin_lat, origin_lon), (dest_lat, dest_lon)).km
        return {
            "status": "success",
            "distance_km": round(dist_km, 2),
            "duration_min": round(dist_km * 2.5, 1),  # Estimate 2.5 min per km
            "geometry": None
        }
    
    try:
        coords = ((origin_lon, origin_lat), (dest_lon, dest_lat))
        route = client.directions(coords, profile="driving-car")

        summary  = route["routes"][0]["summary"]
        geometry = route["routes"][0]["geometry"]

        return {
            "status":       "success",
            "distance_km":  round(summary["distance"] / 1000, 2),
            "duration_min": round(summary["duration"] / 60, 1),
            "geometry":     geometry
        }
    except Exception as e:
        return {
            "status":  "error",
            "message": str(e),
            "distance_km": 0,
            "duration_min": 0,
            "geometry":     None
        }


def get_full_evacuation_plan(origin_lat, origin_lon, zone_name="Your Location"):
    """
    Complete evacuation plan for a location:
    - Finds 3 nearest safe zones
    - Gets road route to closest one
    - Returns full plan with instructions
    """
    # Step 1: Find nearest safe zones
    nearest = find_nearest_safe_zones(origin_lat, origin_lon, top_n=3)

    # Step 2: Get road route to closest safe zone
    primary = nearest[0]
    route = get_evacuation_route(
        origin_lat, origin_lon,
        primary["lat"], primary["lon"]
    )

    # Step 3: Build evacuation instructions
    instructions = [
        f"Leave {zone_name} immediately",
        f"Head towards {primary['name']}",
        f"Distance: {route['distance_km']} km",
        f"Estimated travel time: {route['duration_min']} minutes by road",
        f"Elevation at safe zone: {primary['elevation']}m (safe from flooding)",
        f"Capacity: {primary['capacity']:,} people",
        "Take essential documents, medicines, and 3 days of supplies",
        "Keep emergency radio on for updates",
        "Call NDRF: 011-24363260 if you need rescue assistance",
    ]

    return {
        "origin_name":    zone_name,
        "origin_lat":     origin_lat,
        "origin_lon":     origin_lon,
        "primary_safe_zone": {
            **primary,
            "road_distance_km":  route["distance_km"],
            "road_duration_min": route["duration_min"],
            "route_geometry":    route["geometry"],
        },
        "alternate_safe_zones": nearest[1:],
        "instructions":   instructions,
        "emergency_contacts": {
            "NDRF":           "011-24363260",
            "State Disaster": "1070",
            "Fire":           "101",
            "Ambulance":      "108",
            "Police":         "100",
        }
    }


# ─── TEST ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("FloodSense Pro — Evacuation Routing Test")
    print("=" * 50)

    # Test from Bellandur (HIGH risk zone)
    print("\n[TEST] Evacuation plan from Bellandur:")
    plan = get_full_evacuation_plan(
        origin_lat=12.9261,
        origin_lon=77.6760,
        zone_name="Bellandur"
    )

    primary = plan["primary_safe_zone"]
    print(f"\n  📍 From        : {plan['origin_name']}")
    print(f"  🏔️  Safe Zone   : {primary['name']}")
    print(f"  📏 Distance    : {primary['road_distance_km']} km by road")
    print(f"  ⏱️  Travel Time : {primary['road_duration_min']} minutes")
    print(f"  ⛰️  Elevation   : {primary['elevation']}m")
    print(f"  👥 Capacity    : {primary['capacity']:,} people")

    print("\n  📋 Instructions:")
    for i, inst in enumerate(plan["instructions"], 1):
        print(f"     {i}. {inst}")

    print("\n  🆘 Emergency Contacts:")
    for name, number in plan["emergency_contacts"].items():
        print(f"     {name:<16}: {number}")

    print("\n  🗺️  Alternate Safe Zones:")
    for z in plan["alternate_safe_zones"]:
        print(f"     - {z['name']} ({z['straight_distance_km']} km away, {z['elevation']}m elevation)")

    print("\n✅ Evacuation routing ready!")