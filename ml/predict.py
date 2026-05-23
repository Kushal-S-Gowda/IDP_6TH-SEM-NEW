# FloodSense Pro — Live prediction (physics + ML ensemble)
# All hydrology: ml/hydrology.py (TWI, SCS-CN, HAND, AHP-FHI, Rational Q, Manning)
# Logs: operational audit only — NOT used for model training (see prediction_log.py)

import os
import sys

import joblib
import numpy as np
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from ml.hydrology import (
    ACTIVE_RAIN_24H_MM,
    HydrologyTrace,
    ensemble_risk_class,
    fhi_to_risk_class,
    run_full_hydrology,
    soil_saturation_theta,
)

MODEL_PATH = "ml/models/best_model.pkl"
SCALER_PATH = "ml/models/scaler.pkl"

# Base weather/geography inputs to XGBoost
ML_FEATURE_NAMES = [
    "rainfall_24h",
    "rainfall_7d",
    "temperature",
    "humidity",
    "wind_speed",
    "elevation",
    "river_proximity",
    "flood_history_freq",
    "soil_saturation_idx",
    "population_density",
]

# Engineered hydrology features (fed to model when scaler trained with 16 features)
ENGINEERED_FEATURE_NAMES = [
    "twi",
    "scs_runoff_mm",
    "scs_runoff_ratio",
    "fhi",
    "hand_m",
    "soil_saturation_theta",
]

ALL_ML_FEATURES = ML_FEATURE_NAMES + ENGINEERED_FEATURE_NAMES

MODEL_AVAILABLE = False
_model = None
_scaler = None
_scaler_n_features = 10

try:
    _model = joblib.load(MODEL_PATH)
    _scaler = joblib.load(SCALER_PATH)
    _scaler_n_features = getattr(_scaler, "n_features_in_", 10)
    MODEL_AVAILABLE = True
except Exception:
    _model = _scaler = None
    MODEL_AVAILABLE = False

RISK_LABELS = {
    0: {
        "label": "LOW",
        "color": "green",
        "hex": "#28a745",
        "action": "No immediate action required. Monitor conditions.",
    },
    1: {
        "label": "MEDIUM",
        "color": "yellow",
        "hex": "#ffc107",
        "action": "Elevated risk. Pre-position resources and issue advisory.",
    },
    2: {
        "label": "HIGH",
        "color": "orange",
        "hex": "#fd7e14",
        "action": "Flood likely within 24 hours. Begin evacuation of vulnerable areas.",
    },
    3: {
        "label": "EXTREME",
        "color": "red",
        "hex": "#dc3545",
        "action": "Imminent catastrophic flood. Activate full emergency protocol immediately.",
    },
}


def _build_feature_vector(
    rainfall_24h,
    rainfall_7d,
    temperature,
    humidity,
    wind_speed,
    elevation,
    river_proximity,
    flood_history_freq,
    soil_saturation_idx,
    population_density,
    trace: HydrologyTrace,
):
    base = [
        rainfall_24h,
        rainfall_7d,
        temperature,
        humidity,
        wind_speed,
        elevation,
        river_proximity,
        flood_history_freq,
        soil_saturation_idx,
        population_density,
    ]
    if _scaler_n_features <= 10:
        return np.array([base], dtype=np.float64)
    eng = [
        trace.twi,
        trace.scs_runoff_mm,
        trace.scs_runoff_ratio,
        trace.fhi,
        trace.hand_m,
        trace.soil_saturation_theta,
    ]
    return np.array([base + eng], dtype=np.float64)


def get_accumulated_rainfall(lat, lon, api_key):
    """OWM 5-day/3h forecast → 6h, 24h, 7d cumulative rainfall [mm]."""
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
            timeout=10,
        )
        r.raise_for_status()
        vals = [float(i.get("rain", {}).get("3h", 0.0)) for i in r.json().get("list", [])]
        if not vals:
            return None, None, None
        return (
            round(sum(vals[:2]), 3),
            round(sum(vals[:8]), 3),
            round(sum(vals) * 7.0 / 5.0, 3),
        )
    except Exception:
        return None, None, None


def _imd_fallback_rainfall(rain_1h_mm):
    """IMD intensity-duration estimate when OWM forecast unavailable."""
    r1 = float(rain_1h_mm)
    if r1 <= 0:
        return 0.0, 0.0, 0.0
    if r1 > 35.5:
        mult, r6 = 10.0, r1 * 3.0
    elif r1 > 7.5:
        mult, r6 = 8.0, r1 * 4.0
    elif r1 > 2.5:
        mult, r6 = 6.0, r1 * 3.0
    else:
        mult, r6 = 4.0, r1 * 2.0
    r24 = round(min(r1 * mult, 204.4), 3)
    return round(min(r6, r24), 3), r24, round(r24 * 4.0, 3)


def _susceptibility_from_fhi(fhi):
    rc = fhi_to_risk_class(fhi)
    return rc, RISK_LABELS[rc]["label"]


def predict_risk(
    rainfall_24h,
    rainfall_7d,
    temperature,
    humidity,
    wind_speed,
    elevation,
    river_proximity,
    flood_history_freq,
    soil_saturation_idx,
    population_density,
):
    """
    Core prediction pipeline:
      1. run_full_hydrology() → TWI, SCS-CN, HAND, FHI, Rational Q, Manning (ml/hydrology.py)
      2. XGBoost on scaled features (if model present)
      3. ensemble_risk_class() → 0.55·ML + 0.45·physics (Mohammed et al. 2025 hybrid pattern)
      4. Dry rule: rainfall_24h < 5 mm → active LOW, susceptibility from FHI retained
    """
    trace = run_full_hydrology(
        float(rainfall_24h),
        float(rainfall_7d),
        float(elevation),
        float(river_proximity),
        float(flood_history_freq),
        float(population_density),
    )
    hydro = trace.to_dict()
    hydro["fhi_factors"] = {
        "f_rain": trace.f_rain,
        "f_twi": trace.f_twi,
        "f_hand": trace.f_hand,
        "f_riv": trace.f_river,
        "f_soil": trace.f_soil,
        "f_hist": trace.f_hist,
        "f_pop": trace.f_pop,
    }

    if float(rainfall_24h) < ACTIVE_RAIN_24H_MM:
        sus_rc, sus_label = _susceptibility_from_fhi(trace.fhi)
        return {
            **hydro,
            "risk_class": 0,
            "risk_label": "LOW",
            "risk_color": RISK_LABELS[0]["color"],
            "risk_hex": RISK_LABELS[0]["hex"],
            "risk_score": round(max(5.0, (1.0 - trace.fhi) * 15.0), 2),
            "action": RISK_LABELS[0]["action"],
            "probabilities": {"LOW": 92.0, "MEDIUM": 5.0, "HIGH": 2.0, "EXTREME": 1.0},
            "model_used": "zero_rain_override" if rainfall_24h == 0 else "dry_weather_override",
            "fusion_method": "dry_weather_rule",
            "susceptibility_class": sus_rc,
            "susceptibility_label": sus_label,
            "susceptibility_fhi": trace.fhi,
            "dry_weather_note": (
                "No significant rainfall in forecast window. Static susceptibility (TWI/FHI/HAND) "
                f"is {sus_label}; active flood risk is LOW."
            ),
        }

    rc_fhi = fhi_to_risk_class(trace.fhi)
    ml_class = None
    all_probs = None
    score = round(trace.fhi * 100.0, 2)
    fusion = "physics_only"

    if MODEL_AVAILABLE and _model is not None and _scaler is not None:
        feats = _build_feature_vector(
            rainfall_24h,
            rainfall_7d,
            temperature,
            humidity,
            wind_speed,
            elevation,
            river_proximity,
            flood_history_freq,
            soil_saturation_idx,
            population_density,
            trace,
        )
        feats_s = _scaler.transform(feats)
        ml_class = int(_model.predict(feats_s)[0])
        probs = _model.predict_proba(feats_s)[0]
        all_probs = {
            RISK_LABELS[i]["label"]: round(float(p) * 100.0, 2) for i, p in enumerate(probs)
        }
        score = round(float(probs[ml_class]) * 100.0, 2)

    rc, fusion = ensemble_risk_class(ml_class, trace.fhi, float(rainfall_24h))
    if all_probs is None:
        p_main = round(trace.fhi * 70.0, 1)
        p_rest = round((100.0 - p_main) / 3.0, 1)
        all_probs = {RISK_LABELS[i]["label"]: (p_main if i == rc_fhi else p_rest) for i in range(4)}

    sus_rc, sus_label = _susceptibility_from_fhi(trace.fhi)
    model_used = "xgboost+hydrology_ensemble" if ml_class is not None else "hydrology_physics"

    return {
        **hydro,
        "risk_class": rc,
        "risk_label": RISK_LABELS[rc]["label"],
        "risk_color": RISK_LABELS[rc]["color"],
        "risk_hex": RISK_LABELS[rc]["hex"],
        "risk_score": score,
        "action": RISK_LABELS[rc]["action"],
        "probabilities": all_probs,
        "model_used": model_used,
        "fusion_method": fusion,
        "ml_class_raw": ml_class,
        "physics_class_raw": rc_fhi,
        "susceptibility_class": sus_rc,
        "susceptibility_label": sus_label,
        "susceptibility_fhi": trace.fhi,
    }


def predict_risk_from_weather(weather_data, zone_data, api_key=None):
    from prediction_log import log_prediction

    lat = zone_data.get("lat", 12.9716)
    lon = zone_data.get("lon", 77.5946)
    rainfall_6h = rainfall_24h = rainfall_7d = None
    data_source = "unknown"

    if api_key:
        rainfall_6h, rainfall_24h, rainfall_7d = get_accumulated_rainfall(lat, lon, api_key)
        if rainfall_24h is not None:
            data_source = "owm_forecast_api"

    if rainfall_24h is None:
        rainfall_6h, rainfall_24h, rainfall_7d = _imd_fallback_rainfall(weather_data.get("rain_1h", 0))
        data_source = "imd_intensity_estimate"

    temperature = float(weather_data.get("temp", 28))
    humidity = float(weather_data.get("humidity", 70))
    wind_speed = float(weather_data.get("wind_kmh", 10)) / 3.6
    elevation = float(zone_data.get("elevation", 900))
    river_proximity = float(zone_data.get("river_proximity", 5))
    flood_history_freq = float(zone_data.get("flood_history", 0.3))
    population_density = float(zone_data.get("population", 30000))
    soil_saturation_idx = soil_saturation_theta(float(rainfall_7d))

    result = predict_risk(
        rainfall_24h,
        rainfall_7d,
        temperature,
        humidity,
        wind_speed,
        elevation,
        river_proximity,
        flood_history_freq,
        soil_saturation_idx,
        population_density,
    )
    result.update(
        {
            "rainfall_6h": rainfall_6h,
            "rainfall_24h": rainfall_24h,
            "rainfall_7d": rainfall_7d,
            "data_source": data_source,
        }
    )

    log_prediction(
        zone_name=zone_data.get("name", "Unknown"),
        features={
            "rainfall_6h": rainfall_6h,
            "rainfall_24h": rainfall_24h,
            "rainfall_7d": rainfall_7d,
            "temperature": temperature,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "elevation": elevation,
            "river_proximity": river_proximity,
            "flood_history_freq": flood_history_freq,
            "soil_saturation_idx": soil_saturation_idx,
            "population": population_density,
        },
        result={**result, "data_source": data_source},
    )
    return result


def predict_all_zones(zones_with_weather):
    results = []
    for zone in zones_with_weather:
        prediction = predict_risk_from_weather(zone, zone, api_key=config.OPENWEATHER_API_KEY)
        results.append({**zone, **prediction})
    return results


# Re-export for tests and legacy imports
from ml.hydrology import compute_fhi, compute_twi  # noqa: E402

def compute_scs_runoff(rainfall_24h_mm, population_density, rainfall_7d_mm=0):
    t = run_full_hydrology(
        rainfall_24h_mm, rainfall_7d_mm, 920.0, 3.0, 0.3, population_density
    )
    return t.scs_runoff_mm, t.scs_runoff_ratio


if __name__ == "__main__":
    print("FloodSense Pro — Prediction (ml/hydrology.py + optional XGBoost ensemble)")
    print("=" * 64)
    cases = [
        ("Dry May Bengaluru", 2, 8, 30, 45, 10, 920, 3.0, 0.2, 0.016, 30000),
        ("Heavy monsoon Bellandur", 95, 380, 24, 92, 35, 887, 0.5, 0.9, 0.76, 45000),
        ("Extreme event", 180, 650, 22, 99, 55, 887, 0.2, 0.95, 0.99, 45000),
    ]
    for name, r24, r7, t, h, w, elev, riv, hist, soil, pop in cases:
        res = predict_risk(r24, r7, t, h, w, elev, riv, hist, soil, pop)
        print(f"\n{name}")
        print(f"  TWI={res['twi']:.4f}  HAND={res['hand_m']:.2f}m  FHI={res['fhi']:.6f}")
        print(f"  SCS Q={res['scs_runoff_mm']:.3f}mm  CN_eff={res['cn_effective']:.1f}  AMC={res['amc_class']}")
        print(f"  Rational Qp={res['rational_Q_m3s']:.4f} m³/s  Manning V={res['manning_drainage_index']:.4f} m/s")
        print(f"  Risk: {res['risk_label']}  Fusion: {res.get('fusion_method')}  Model: {res['model_used']}")
