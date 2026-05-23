# FloodSense Pro — Resource Optimization Engine
# Uses Linear Programming (PuLP) to allocate disaster resources optimally

try:
    import pulp
    PULP_AVAILABLE = True
except ImportError as e:
    # Keep app running even if PuLP is not installed; fall back to simple allocation.
    PULP_AVAILABLE = False

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

RISK_WEIGHTS = {0: 0.5, 1: 1.5, 2: 3.0, 3: 4.0}
RISK_LABELS  = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "EXTREME"}

def allocate_resources(zones_with_risk, available_resources):
    """
    Optimally allocate disaster resources across zones.

    zones_with_risk: list of dicts, each with:
        - name, population, risk_class, lat, lon

    available_resources: dict with:
        - ambulances, boats, camp_beds, food_units, medical_teams

    Returns: list of zones with allocated resources + deployment plan
    """
    if not PULP_AVAILABLE:
        return simple_allocation(zones_with_risk, available_resources)

    # Filter only zones needing resources (MEDIUM and above)
    active_zones = [z for z in zones_with_risk if z["risk_class"] >= 1]

    if not active_zones:
        return [], {"message": "All zones LOW risk. No deployment needed."}

    # ── Setup LP Problem ────────────────────────────────────
    prob = pulp.LpProblem("FloodResourceAllocation", pulp.LpMaximize)

    zone_names = [z["name"] for z in active_zones]
    n = len(zone_names)

    # ── Decision Variables ──────────────────────────────────
    # Each variable = number of resource units to send to each zone
    ambulances   = {z: pulp.LpVariable(f"amb_{z}",   lowBound=0, cat="Integer") for z in zone_names}
    boats        = {z: pulp.LpVariable(f"boat_{z}",  lowBound=0, cat="Integer") for z in zone_names}
    camp_beds    = {z: pulp.LpVariable(f"camp_{z}",  lowBound=0, cat="Integer") for z in zone_names}
    food_units   = {z: pulp.LpVariable(f"food_{z}",  lowBound=0, cat="Integer") for z in zone_names}
    med_teams    = {z: pulp.LpVariable(f"med_{z}",   lowBound=0, cat="Integer") for z in zone_names}

    # ── Objective: Maximize weighted population coverage ────
    prob += pulp.lpSum(
        (ambulances[z["name"]] + boats[z["name"]] + med_teams[z["name"]]) *
        z["population"] * RISK_WEIGHTS[z["risk_class"]]
        for z in active_zones
    )

    # ── Constraints ─────────────────────────────────────────

    # 1. Total resources cannot exceed availability
    prob += pulp.lpSum(ambulances[z] for z in zone_names)  <= available_resources["ambulances"]
    prob += pulp.lpSum(boats[z] for z in zone_names)       <= available_resources["boats"]
    prob += pulp.lpSum(camp_beds[z] for z in zone_names)   <= available_resources["camp_beds"]
    prob += pulp.lpSum(food_units[z] for z in zone_names)  <= available_resources["food_units"]
    prob += pulp.lpSum(med_teams[z] for z in zone_names)   <= available_resources["medical_teams"]

    # 2. HIGH and EXTREME zones must get minimum resources
    for z in active_zones:
        if z["risk_class"] >= 2:  # HIGH or EXTREME
            prob += ambulances[z["name"]]  >= 1
            prob += med_teams[z["name"]]   >= 1
            prob += camp_beds[z["name"]]   >= 50

    # 3. EXTREME zones get proportionally more
    extreme_zones = [z for z in active_zones if z["risk_class"] == 3]
    high_zones    = [z for z in active_zones if z["risk_class"] == 2]

    if extreme_zones and available_resources["ambulances"] >= 4:
        prob += pulp.lpSum(ambulances[z["name"]] for z in extreme_zones) >= \
               int(available_resources["ambulances"] * 0.35)

    # ── Solve ───────────────────────────────────────────────
    pulp.LpProblem.solve(prob, pulp.PULP_CBC_CMD(msg=0))

    if pulp.LpStatus[prob.status] != "Optimal":
        # Fallback: proportional allocation
        return proportional_fallback(active_zones, available_resources)

    # ── Build Results ────────────────────────────────────────
    allocation_results = []
    priority = 1

    # Sort by risk (EXTREME first) then population
    sorted_zones = sorted(active_zones,
                          key=lambda z: (z["risk_class"], z["population"]),
                          reverse=True)

    for z in sorted_zones:
        name = z["name"]
        allocated_amb   = int(ambulances[name].value()  or 0)
        allocated_boat  = int(boats[name].value()       or 0)
        allocated_camp  = int(camp_beds[name].value()   or 0)
        allocated_food  = int(food_units[name].value()  or 0)
        allocated_med   = int(med_teams[name].value()   or 0)

        # Only include zones that got resources
        if allocated_amb + allocated_boat + allocated_camp + allocated_food + allocated_med > 0:
            allocation_results.append({
                **z,
                "priority":       priority,
                "ambulances":     allocated_amb,
                "boats":          allocated_boat,
                "camp_beds":      allocated_camp,
                "food_units":     allocated_food,
                "medical_teams":  allocated_med,
                "risk_label":     RISK_LABELS[z["risk_class"]],
            })
            priority += 1

    # ── Summary stats ────────────────────────────────────────
    summary = {
        "status":           "Optimal",
        "zones_served":     len(allocation_results),
        "ambulances_used":  sum(r["ambulances"]    for r in allocation_results),
        "boats_used":       sum(r["boats"]         for r in allocation_results),
        "camp_beds_used":   sum(r["camp_beds"]     for r in allocation_results),
        "food_units_used":  sum(r["food_units"]    for r in allocation_results),
        "med_teams_used":   sum(r["medical_teams"] for r in allocation_results),
        "total_population_covered": sum(r["population"] for r in allocation_results),
    }

    return allocation_results, summary


def simple_allocation(zones_with_risk, available_resources):
    """Simple allocation when PuLP is not available."""
    # Filter only zones needing resources (MEDIUM and above)
    active_zones = [z for z in zones_with_risk if z["risk_class"] >= 1]
    
    if not active_zones:
        return [], {"message": "All zones LOW risk. No deployment needed."}
    
    # Sort by risk (EXTREME first) then population
    sorted_zones = sorted(active_zones,
                          key=lambda z: (z["risk_class"], z["population"]),
                          reverse=True)
    
    allocation_results = []
    remaining_resources = available_resources.copy()
    
    for i, z in enumerate(sorted_zones):
        allocated = {}
        
        # Minimum allocation for HIGH and EXTREME zones
        if z["risk_class"] >= 2:
            allocated["ambulances"] = min(remaining_resources["ambulances"], 2)
            allocated["medical_teams"] = min(remaining_resources["medical_teams"], 2)
            allocated["camp_beds"] = min(remaining_resources["camp_beds"], 100)
        else:
            allocated["ambulances"] = min(remaining_resources["ambulances"], 1)
            allocated["medical_teams"] = min(remaining_resources["medical_teams"], 1)
            allocated["camp_beds"] = min(remaining_resources["camp_beds"], 50)
        
        # Allocate boats and food proportionally
        allocated["boats"] = max(0, min(remaining_resources["boats"], 
                                       int(remaining_resources["boats"] * 0.3)))
        allocated["food_units"] = max(0, min(remaining_resources["food_units"], 
                                           int(remaining_resources["food_units"] * 0.3)))
        
        # Update remaining resources
        for key in allocated:
            remaining_resources[key] -= allocated[key]
        
        # Only include zones that got resources
        if sum(allocated.values()) > 0:
            allocation_results.append({
                **z,
                "priority": i + 1,
                "risk_label": RISK_LABELS[z["risk_class"]],
                **allocated
            })
    
    summary = {
        "status": "Simple (fallback)",
        "zones_served": len(allocation_results),
        "ambulances_used": sum(r.get("ambulances", 0) for r in allocation_results),
        "boats_used": sum(r.get("boats", 0) for r in allocation_results),
        "camp_beds_used": sum(r.get("camp_beds", 0) for r in allocation_results),
        "food_units_used": sum(r.get("food_units", 0) for r in allocation_results),
        "med_teams_used": sum(r.get("medical_teams", 0) for r in allocation_results),
        "total_population_covered": sum(r["population"] for r in allocation_results),
    }
    
    return allocation_results, summary


def proportional_fallback(zones, resources):
    """Fallback if LP fails — simple proportional allocation."""
    total_weight = sum(RISK_WEIGHTS[z["risk_class"]] * z["population"] for z in zones)
    results = []
    for i, z in enumerate(sorted(zones,
                                  key=lambda x: (x["risk_class"], x["population"]),
                                  reverse=True)):
        weight = RISK_WEIGHTS[z["risk_class"]] * z["population"] / total_weight
        results.append({
            **z,
            "priority":      i + 1,
            "ambulances":    max(1, int(resources["ambulances"]    * weight)),
            "boats":         max(0, int(resources["boats"]         * weight)),
            "camp_beds":     max(50, int(resources["camp_beds"]    * weight)),
            "food_units":    max(100, int(resources["food_units"]  * weight)),
            "medical_teams": max(1, int(resources["medical_teams"] * weight)),
            "risk_label":    RISK_LABELS[z["risk_class"]],
        })
    summary = {"status": "Proportional (fallback)", "zones_served": len(results)}
    return results, summary


# ─── TEST ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("FloodSense Pro — Resource Optimization Engine Test")
    print("=" * 58)

    # Simulate flood scenario with risk predictions
    test_zones = [
        {"name": "Bellandur",    "lat": 12.9261, "lon": 77.6760, "population": 45000, "risk_class": 3},
        {"name": "Marathahalli", "lat": 12.9591, "lon": 77.6972, "population": 32000, "risk_class": 2},
        {"name": "HSR Layout",   "lat": 12.9116, "lon": 77.6389, "population": 28000, "risk_class": 2},
        {"name": "Whitefield",   "lat": 12.9698, "lon": 77.7499, "population": 55000, "risk_class": 1},
        {"name": "Koramangala",  "lat": 12.9279, "lon": 77.6271, "population": 38000, "risk_class": 1},
        {"name": "BTM Layout",   "lat": 12.9166, "lon": 77.6101, "population": 42000, "risk_class": 2},
        {"name": "Indiranagar",  "lat": 12.9719, "lon": 77.6412, "population": 25000, "risk_class": 0},
    ]

    # Available resources (entered by authority user)
    resources = {
        "ambulances":    45,
        "boats":          8,
        "camp_beds":    1500,
        "food_units":   5000,
        "medical_teams": 12,
    }

    print("\n📦 Available Resources:")
    for k, v in resources.items():
        print(f"   {k:<16}: {v}")

    print("\n⚙️  Running optimization...")
    allocation, summary = allocate_resources(test_zones, resources)

    print(f"\n✅ Status          : {summary['status']}")
    print(f"   Zones served    : {summary['zones_served']}")
    print(f"   Ambulances used : {summary['ambulances_used']} / {resources['ambulances']}")
    print(f"   Boats used      : {summary['boats_used']} / {resources['boats']}")
    print(f"   Camp beds used  : {summary['camp_beds_used']} / {resources['camp_beds']}")
    print(f"   Population covered: {summary['total_population_covered']:,}")

    print("\n📋 DEPLOYMENT PLAN:")
    print("=" * 75)
    for r in allocation:
        print(f"\n  PRIORITY {r['priority']} — {r['name']} [{r['risk_label']} RISK]")
        print(f"  Population at risk : {r['population']:,}")
        print(f"  Ambulances         : {r['ambulances']} units")
        print(f"  Rescue Boats       : {r['boats']} units")
        print(f"  Camp Beds          : {r['camp_beds']} beds")
        print(f"  Food Units         : {r['food_units']} units")
        print(f"  Medical Teams      : {r['medical_teams']} teams")
    print("=" * 75)
    print("\n🏆 Optimization Engine ready!")