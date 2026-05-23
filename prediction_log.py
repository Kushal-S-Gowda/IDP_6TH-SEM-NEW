# FloodSense Pro — Operational prediction audit log (CSV)
#
# PURPOSE: Traceability for evaluator / incident review — records inputs and outputs
#          each time predict_risk_from_weather() runs (typically every 30s per zone).
#
# NOT USED FOR MODEL TRAINING. Training data is generated separately in
# ml/preprocess.py → data/processed/flood_dataset.csv using Monte Carlo + hydrology labels.
# Live OWM 3h forecast slots are consumed at inference time only.

import csv
import os
from datetime import datetime

LOG_PATH = "logs/prediction_log.csv"

HEADERS = [
    "timestamp",
    "zone_name",
    "rainfall_6h_mm",
    "rainfall_24h_mm",
    "rainfall_7d_mm",
    "temperature_c",
    "humidity_pct",
    "wind_speed_ms",
    "elevation_m",
    "river_proximity_km",
    "flood_history_freq",
    "soil_saturation_idx",
    "population",
    "twi",
    "hand_m",
    "scs_runoff_mm",
    "cn_effective",
    "fhi",
    "imd_24h_class",
    "rational_Q_m3s",
    "risk_label",
    "risk_class",
    "confidence_pct",
    "model_used",
    "fusion_method",
    "data_source",
    "log_purpose",
]


def log_prediction(zone_name, features, result):
    os.makedirs("logs", exist_ok=True)
    file_exists = os.path.isfile(LOG_PATH)

    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "zone_name": zone_name,
                "rainfall_6h_mm": features.get("rainfall_6h", features.get("forecast_rain_6h", 0)),
                "rainfall_24h_mm": features.get("rainfall_24h", features.get("forecast_rain_24h", 0)),
                "rainfall_7d_mm": features.get("rainfall_7d", features.get("forecast_rain_7d", 0)),
                "temperature_c": features.get("temperature", 0),
                "humidity_pct": features.get("humidity", 0),
                "wind_speed_ms": features.get("wind_speed", features.get("wind_speed_ms", 0)),
                "elevation_m": features.get("elevation", 0),
                "river_proximity_km": features.get("river_proximity", 0),
                "flood_history_freq": features.get("flood_history_freq", 0),
                "soil_saturation_idx": features.get("soil_saturation_idx", 0),
                "population": features.get("population", 0),
                "twi": result.get("twi", ""),
                "hand_m": result.get("hand_m", ""),
                "scs_runoff_mm": result.get("scs_runoff_mm", ""),
                "cn_effective": result.get("cn_effective", ""),
                "fhi": result.get("fhi", ""),
                "imd_24h_class": result.get("imd_24h_class", ""),
                "rational_Q_m3s": result.get("rational_Q_m3s", ""),
                "risk_label": result.get("risk_label", "UNKNOWN"),
                "risk_class": result.get("risk_class", -1),
                "confidence_pct": result.get("risk_score", 0),
                "model_used": result.get("model_used", "unknown"),
                "fusion_method": result.get("fusion_method", ""),
                "data_source": result.get("data_source", "unknown"),
                "log_purpose": "operational_audit_not_training",
            }
        )


def get_recent_logs(limit=50):
    if not os.path.isfile(LOG_PATH):
        return []
    with open(LOG_PATH, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return list(reversed(rows))[:limit]


def get_log_stats():
    if not os.path.isfile(LOG_PATH):
        return {"total": 0, "zones": [], "risk_counts": {}, "log_path": LOG_PATH}
    with open(LOG_PATH, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    zones = sorted({r.get("zone_name", "") for r in rows if r.get("zone_name")})
    risk_counts = {}
    for r in rows:
        lbl = r.get("risk_label", "UNKNOWN")
        risk_counts[lbl] = risk_counts.get(lbl, 0) + 1
    return {
        "total": len(rows),
        "zones": zones,
        "risk_counts": risk_counts,
        "log_path": LOG_PATH,
        "purpose": "operational_audit_not_training",
    }
