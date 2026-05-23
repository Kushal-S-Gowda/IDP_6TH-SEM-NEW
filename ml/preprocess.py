# FloodSense Pro — Training data generation (physics-grounded labels)
# Labels derived from ml/hydrology.py — NOT from arbitrary rules.
# Training CSV: data/processed/flood_dataset.csv
# Live logs: logs/prediction_log.csv — operational only, NOT fed back into training.

import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.hydrology import (
    AHP_WEIGHTS,
    CN_BY_LANDUSE,
    cn_from_population_density,
    fhi_to_risk_class,
    run_full_hydrology,
    soil_saturation_theta,
)

np.random.seed(42)

# Features fed to XGBoost (16 = 10 base + 6 engineered hydrology outputs)
BASE_FEATURES = [
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

ENGINEERED_FEATURES = [
    "twi",
    "scs_runoff_mm",
    "scs_runoff_ratio",
    "fhi",
    "hand_m",
    "soil_saturation_theta",
]

ML_FEATURES = BASE_FEATURES + ENGINEERED_FEATURES


def generate_flood_dataset(n_samples: int = 5000) -> pd.DataFrame:
    """
    Monte Carlo sampling over weather/geography space; each row label = fhi_to_risk_class(FHI)
    where FHI comes from full SCS-CN + TWI + HAND + AHP pipeline (ml/hydrology.py).
    """
    print("Generating hydrologically-grounded flood dataset...")
    print("  Equations: TWI | SCS-CN TR-55 | HAND | AHP-FHI | Rational Q | Manning")
    data = []

    for _ in range(n_samples):
        rainfall_24h = float(np.clip(np.random.exponential(scale=18), 0, 250))
        amc_5day = float(np.clip(np.random.exponential(scale=25), 0, 150))
        rainfall_7d = float(np.clip(rainfall_24h * np.random.uniform(2.5, 7.0) + amc_5day, 0, 700))
        temperature = float(np.random.normal(28.5, 5.5))
        humidity = float(np.random.uniform(35, 100))
        wind_speed = float(np.clip(np.random.exponential(12), 0, 100))
        elevation = float(np.clip(np.random.normal(915, 25), 870, 960))
        river_proximity = float(np.clip(np.random.exponential(3), 0.1, 20))
        flood_history_freq = float(np.random.beta(2, 5))
        population_density = float(np.clip(np.random.normal(35000, 12000), 5000, 55000))
        soil_idx = soil_saturation_theta(rainfall_7d)

        trace = run_full_hydrology(
            rainfall_24h,
            rainfall_7d,
            elevation,
            river_proximity,
            flood_history_freq,
            population_density,
        )
        risk_level = fhi_to_risk_class(trace.fhi)

        data.append(
            {
                "rainfall_24h": round(rainfall_24h, 3),
                "rainfall_7d": round(rainfall_7d, 3),
                "temperature": round(temperature, 2),
                "humidity": round(humidity, 2),
                "wind_speed": round(wind_speed, 3),
                "elevation": round(elevation, 2),
                "river_proximity": round(river_proximity, 3),
                "flood_history_freq": round(flood_history_freq, 4),
                "soil_saturation_idx": round(soil_idx, 6),
                "population_density": round(population_density, 0),
                "twi": trace.twi,
                "scs_runoff_mm": trace.scs_runoff_mm,
                "scs_runoff_ratio": trace.scs_runoff_ratio,
                "fhi": trace.fhi,
                "hand_m": trace.hand_m,
                "soil_saturation_theta": trace.soil_saturation_theta,
                "cn_effective": trace.cn_effective,
                "amc_class": trace.amc_class,
                "imd_24h_class": trace.imd_24h_class,
                "rational_Q_m3s": trace.rational_Q_m3s,
                "risk_level": risk_level,
            }
        )

    return pd.DataFrame(data)


def preprocess_and_split(df: pd.DataFrame):
    print("Preprocessing — MinMaxScaler on", len(ML_FEATURES), "features")
    X = df[ML_FEATURES]
    y = df["risk_level"]
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42, stratify=y
    )
    os.makedirs("ml/models", exist_ok=True)
    joblib.dump(scaler, "ml/models/scaler.pkl")
    print("  Scaler saved -> ml/models/scaler.pkl (n_features=", scaler.n_features_in_, ")")
    return X_train, X_test, y_train, y_test, scaler


def show_dataset_stats(df: pd.DataFrame):
    print("\n-- Dataset Summary -----------------------------------------")
    print(f"  Total samples   : {len(df)}")
    print(f"  Label source    : FHI from ml/hydrology.py (SCS-CN + TWI + AHP)")
    labels = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "EXTREME"}
    for level, count in df["risk_level"].value_counts().sort_index().items():
        pct = count / len(df) * 100
        bar = "#" * int(pct / 2)
        print(f"    {labels[level]:8s} ({level}): {count:5d} ({pct:.1f}%) {bar}")
    print(f"\n  Mean TWI        : {df['twi'].mean():.4f}")
    print(f"  Mean FHI        : {df['fhi'].mean():.6f}")
    print(f"  Mean runoff_mm  : {df['scs_runoff_mm'].mean():.3f}")
    print(f"  Mean HAND [m]   : {df['hand_m'].mean():.3f}")
    print("-------------------------------------------------------------")


# Legacy names used in docs
compute_twi = __import__("ml.hydrology", fromlist=["compute_twi"]).compute_twi
compute_scs_runoff = None  # use run_full_hydrology
compute_flood_hazard_index = None
assign_risk_class = fhi_to_risk_class
AHP_WEIGHTS = AHP_WEIGHTS
CN_URBAN_BENGALURU = CN_BY_LANDUSE


if __name__ == "__main__":
    print("FloodSense Pro — Preprocessing (physics-grounded labels)")
    print("=" * 55)
    df = generate_flood_dataset(n_samples=5000)
    show_dataset_stats(df)
    os.makedirs("data/processed", exist_ok=True)
    df.to_csv("data/processed/flood_dataset.csv", index=False)
    print("\n  Dataset saved -> data/processed/flood_dataset.csv")
    X_train, X_test, y_train, y_test, scaler = preprocess_and_split(df)
    print(f"\n  Training set  : {X_train.shape[0]} samples × {X_train.shape[1]} features")
    print(f"  Test set      : {X_test.shape[0]} samples")
    print("\n  Run: python ml/train_model.py  to retrain XGBoost with 16 features")
