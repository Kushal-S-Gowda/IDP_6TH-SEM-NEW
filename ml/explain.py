# FloodSense Pro — XAI Explainability Module
# Uses SHAP to explain individual XGBoost flood risk predictions
# Place this file at: ml/explain.py

import numpy as np
import joblib
import os

MODEL_PATH  = "ml/models/best_model.pkl"
SCALER_PATH = "ml/models/scaler.pkl"

FEATURE_NAMES = [
    "rainfall_24h", "rainfall_7d", "temperature",
    "humidity", "wind_speed", "elevation",
    "river_proximity", "flood_history_freq",
    "soil_saturation_idx", "population_density"
]

FEATURE_LABELS = {
    "rainfall_24h":        "Rainfall 24h (mm)",
    "rainfall_7d":         "Rainfall 7-day (mm)",
    "temperature":         "Temperature (°C)",
    "humidity":            "Humidity (%)",
    "wind_speed":          "Wind Speed (km/h)",
    "elevation":           "Elevation (m)",
    "river_proximity":     "River Proximity (km)",
    "flood_history_freq":  "Flood History",
    "soil_saturation_idx": "Soil Saturation",
    "population_density":  "Population Density",
}

RISK_LABELS = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "EXTREME"}

# Load model once
_model  = None
_scaler = None

def _load():
    global _model, _scaler
    if _model is None:
        try:
            _model  = joblib.load(MODEL_PATH)
            _scaler = joblib.load(SCALER_PATH)
        except Exception as e:
            print(f"[XAI] Model load failed: {e}")
            _model = None
            _scaler = None

def explain_prediction(feature_values: dict) -> dict:
    """
    Given a dict of feature_name → value, returns:
    {
        risk_label, risk_class, confidence,
        shap_values: [ {feature, label, value, shap, direction, pct} ],
        top_driver: "rainfall_24h",
        explanation_text: "...",
        model_available: True/False
    }
    """
    _load()

    # Build feature array in correct order
    raw = np.array([[feature_values.get(f, 0) for f in FEATURE_NAMES]])

    if _model is None or _scaler is None:
        return _rule_based_explain(feature_values, raw)

    # Scale
    scaled = _scaler.transform(raw)

    # Predict
    pred = _model.predict(scaled)
    risk_class = int(pred[0] if pred.size > 0 else 0)
    prob_pred = _model.predict_proba(scaled)
    probabilities = prob_pred[0] if prob_pred.size > 0 else np.array([0.25, 0.25, 0.25, 0.25])
    confidence = round(float(probabilities[risk_class]) * 100, 1)

    # ── SHAP values ────────────────────────────────────────────────
    try:
        import shap
        explainer   = shap.TreeExplainer(_model)
        shap_vals   = explainer.shap_values(scaled)   # shape: (n_classes, n_samples, n_features)

        # Use SHAP values for the predicted class
        if isinstance(shap_vals, list):
            class_shap = shap_vals[risk_class][0]     # shape: (n_features,)
        else:
            class_shap = shap_vals[0]

        shap_available = True
    except Exception as e:
        print(f"[XAI] SHAP failed, using gradient proxy: {e}")
        shap_available = False
        class_shap = None

    # ── Fallback: feature importance proxy if SHAP unavailable ─────
    if not shap_available or class_shap is None:
        class_shap = _importance_proxy(_model, scaled, risk_class)

    # ── Build output ────────────────────────────────────────────────
    # Convert to regular Python list to avoid numpy issues
    class_shap_list = [float(x) for x in class_shap.flatten()]
    total_abs = sum(abs(v) for v in class_shap_list)
    if total_abs == 0:
        total_abs = 1.0
    items = []
    for i, fname in enumerate(FEATURE_NAMES):
        sv = class_shap_list[i]
        pct = round(abs(sv) / total_abs * 100, 1)
        items.append({
            "feature":   fname,
            "label":     FEATURE_LABELS[fname],
            "value":     round(feature_values.get(fname, 0), 2),
            "shap":      round(sv, 4),
            "direction": "increases" if sv > 0 else "decreases",
            "pct":       pct,
        })

    # Sort by absolute contribution descending
    items.sort(key=lambda x: abs(x["shap"]), reverse=True)

    top_driver = items[0]["feature"] if items else "rainfall_24h"

    explanation_text = _build_explanation(
        items, risk_class, confidence, feature_values
    )

    return {
        "model_available":  True,
        "shap_available":   shap_available,
        "risk_class":       risk_class,
        "risk_label":       RISK_LABELS[risk_class],
        "confidence":       confidence,
        "probabilities":    {RISK_LABELS[i]: round(float(p)*100,1) for i,p in enumerate(probabilities)},
        "shap_values":      items,
        "top_driver":       top_driver,
        "top_driver_label": FEATURE_LABELS[top_driver],
        "explanation_text": explanation_text,
    }


def _importance_proxy(model, scaled, risk_class):
    """
    When SHAP is unavailable, approximate feature contribution using
    tree feature importances × scaled input values.
    Not as accurate as SHAP but gives a reasonable signal.
    """
    try:
        fi = model.feature_importances_   # shape: (n_features,)
        # Directional proxy: positive if scaled value > 0.5, negative if below
        direction = scaled[0] - 0.5       # centre around 0
        proxy = fi * direction
        # Scale up for readability
        return proxy * 10
    except Exception:
        return np.zeros(len(FEATURE_NAMES))


def _rule_based_explain(feature_values, raw):
    """Physics-based XAI when ML/SHAP unavailable — uses ml/hydrology.py AHP factors."""
    from ml.hydrology import AHP_WEIGHTS, fhi_to_risk_class, run_full_hydrology

    r24 = float(feature_values.get("rainfall_24h", 0))
    r7 = float(feature_values.get("rainfall_7d", r24 * 4))
    trace = run_full_hydrology(
        r24,
        r7,
        float(feature_values.get("elevation", 920)),
        float(feature_values.get("river_proximity", 5)),
        float(feature_values.get("flood_history_freq", 0.3)),
        float(feature_values.get("population_density", 30000)),
    )
    risk_class = fhi_to_risk_class(trace.fhi)
    risk_score = round(trace.fhi * 100, 1)

    w = AHP_WEIGHTS
    factor_map = {
        "rainfall_24h": (trace.f_rain, w["rainfall_intensity"]),
        "river_proximity": (trace.f_river, w["river_proximity"]),
        "elevation": (trace.f_hand, w["hand"]),
        "soil_saturation_idx": (trace.f_soil, w["soil_saturation"]),
        "flood_history_freq": (trace.f_hist, w["flood_history"]),
        "population_density": (trace.f_pop, w["population"]),
    }
    items = []
    scores = {}
    for fname, (fval, wt) in factor_map.items():
        scores[fname] = fval * wt * 100
    scores["rainfall_7d"] = trace.f_soil * 50
    scores["humidity"] = 0
    scores["wind_speed"] = 0
    scores["temperature"] = 0
    scores["twi_engineered"] = trace.f_twi * w["twi"] * 100
    total = sum(scores.values()) or 1.0
    for fname in FEATURE_NAMES:
        sc = scores.get(fname, 0)
        items.append({
            "feature":   fname,
            "label":     FEATURE_LABELS[fname],
            "value":     round(feature_values.get(fname, 0), 2),
            "shap":      round(sc / 100, 4),
            "direction": "increases",
            "pct":       round(sc / total * 100, 1),
        })
    items.sort(key=lambda x: x["pct"], reverse=True)

    return {
        "model_available":  False,
        "shap_available":   False,
        "risk_class":       risk_class,
        "risk_label":       RISK_LABELS[risk_class],
        "confidence":       None,
        "probabilities":    {},
        "shap_values":      items,
        "top_driver":       items[0]["feature"],
        "top_driver_label": items[0]["label"],
        "explanation_text": (
            f"AHP-FHI physics (ml/hydrology.py). FHI={trace.fhi:.4f}. "
            f"Top driver: {items[0]['label']}."
        ),
        "hydrology_trace": trace.to_dict(),
    }


def _build_explanation(items, risk_class, confidence, fv):
    """Build a human-readable 2-sentence explanation."""
    top3 = [x for x in items[:3] if x["pct"] > 5]
    drivers = ", ".join(f"{x['label']} ({x['pct']}%)" for x in top3)
    label = RISK_LABELS[risk_class]
    r24 = fv.get("rainfall_24h", 0)
    lake = fv.get("soil_saturation_idx", 0) * 100
    conf_str = f"Model confidence: {confidence}%." if confidence else ""

    if risk_class == 0:
        return f"All indicators within safe range. {conf_str} Primary contributors: {drivers}."
    elif risk_class == 1:
        return f"Elevated risk due to {drivers}. {conf_str} Monitor conditions closely."
    elif risk_class == 2:
        return f"HIGH risk driven primarily by {drivers}. {conf_str} Rainfall {r24:.0f}mm in 24h with saturated soil accelerates surface runoff."
    else:
        return f"EXTREME risk — {drivers} have pushed all indicators past critical thresholds. {conf_str} Immediate action required."


def explain_zone(zone_data, weather_data) -> dict:
    """
    Convenience wrapper: takes zone + weather dicts (same format used
    elsewhere in the app) and returns explanation.
    """
    from ml.predict import get_accumulated_rainfall
    import config as _cfg
    lat = zone_data.get("lat", 12.97)
    lon = zone_data.get("lon", 77.59)
    _, rainfall_24h, rainfall_7d = get_accumulated_rainfall(lat, lon, _cfg.OPENWEATHER_API_KEY)
    if rainfall_24h is None:
        rainfall_24h = weather_data.get("rainfall_1h", 0) * 8
        rainfall_7d = rainfall_24h * 4
    from ml.hydrology import soil_saturation_theta
    features = {
        "rainfall_24h": rainfall_24h,
        "rainfall_7d": rainfall_7d or rainfall_24h * 4,
        "temperature": weather_data.get("temp", weather_data.get("temperature", 28)),
        "humidity": weather_data.get("humidity", 70),
        "wind_speed": weather_data.get("wind_kmh", weather_data.get("wind_speed", 10)),
        "elevation": zone_data.get("elevation", 900),
        "river_proximity": zone_data.get("river_proximity", 3),
        "flood_history_freq": zone_data.get("flood_history", zone_data.get("flood_history_freq", 0.3)),
        "soil_saturation_idx": soil_saturation_theta(float(rainfall_7d or rainfall_24h * 4)),
        "population_density": zone_data.get("population", 20000),
    }
    result = explain_prediction(features)
    result["zone_name"] = zone_data.get("name", "Unknown")
    return result


# ── TEST ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("FloodSense Pro — XAI Module Test")
    print("=" * 50)
    result = explain_prediction({
        "rainfall_24h": 110, "rainfall_7d": 420, "temperature": 24,
        "humidity": 92,      "wind_speed": 18,   "elevation": 887,
        "river_proximity": 0.5, "flood_history_freq": 0.9,
        "soil_saturation_idx": 0.84, "population_density": 35000,
    })
    print(f"Risk: {result['risk_label']} ({result['confidence']}% confidence)")
    print(f"Top driver: {result['top_driver_label']}")
    print(f"Explanation: {result['explanation_text']}")
    print("\nFeature contributions:")
    for item in result["shap_values"][:5]:
        bar = "█" * int(item["pct"] / 3)
        print(f"  {item['label']:<28} {item['pct']:>5.1f}%  {bar}")
    print("\n✅ XAI module ready!")