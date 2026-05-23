# FloodSense Pro — Hydrological & multi-criteria risk engine
# Single source of truth for all equations (evaluator / publication traceability).
#
# Literature alignment (2024–2026):
#   TWI          — Beven & Kirkby (1979); Shahabi et al. (2020); Springer Nat. Hazards 2025
#   SCS-CN       — USDA-NRCS TR-55 (1986); HEC-HMS; urban CN India studies
#   HAND         — Nobre et al. (2011); urban flood susceptibility GIS papers
#   AHP-FHI      — Mohammed et al. (2024) GIS+AHP; MDPI Water 2025; Fuzzy-AHP+ML JUSIFO 2025
#   Rational Q   — Chow, Maidment, Mays (1988) Applied Hydrology
#   Manning n    — open-channel capacity proxy for urban drains
#   IMD bands    — India Meteorological Department rainfall intensity classification
#   Soil θ       — antecedent moisture from 7-day cumulative vs field capacity (laterite Bengaluru)

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple

import numpy as np

# ── Bengaluru calibration constants (documented, not hidden) ─────────────────
BENGALURU_MEAN_ELEVATION_M = 920.0
BENGALURU_ELEV_RANGE_M = (870.0, 960.0)
FIELD_CAPACITY_7D_MM = 480.0  # red laterite urban soil storage capacity proxy (mm/week)
ACTIVE_RAIN_24H_MM = 5.0      # below: no active flood event (IMD light-rain lower band)

# AHP weights — Mohammed et al. (2024) 7-factor urban flood hazard model (sum = 1.0)
AHP_WEIGHTS: Dict[str, float] = {
    "rainfall_intensity": 0.2818,
    "twi": 0.2210,
    "hand": 0.1682,           # elevation / HAND factor (same weight slot as elevation in paper)
    "river_proximity": 0.1356,
    "soil_saturation": 0.0987,
    "flood_history": 0.0612,
    "population": 0.0335,
}
assert abs(sum(AHP_WEIGHTS.values()) - 1.0) < 1e-6

# USDA TR-55 curve numbers — Hydrologic Soil Group C (Bengaluru laterite), urban land use
CN_BY_LANDUSE = {
    "impervious": 92,
    "industrial": 88,
    "residential": 85,
    "lake_buffer": 78,
    "open_space": 74,
}

# IMD 24h accumulated rainfall classification (mm / 24h) — India Meteorological Department
IMD_24H_THRESHOLDS_MM = [
    (204.4, "catastrophic"),
    (150.0, "extremely_heavy"),
    (100.0, "very_heavy"),
    (64.5, "heavy"),
    (35.5, "moderate"),
    (7.5, "light"),
    (0.0, "dry"),
]

FHI_CLASS_THRESHOLDS = (0.25, 0.45, 0.65)  # LOW, MED, HIGH, EXTREME


@dataclass
class HydrologyTrace:
    """Full calculation audit trail returned with every prediction."""
    twi: float
    hand_m: float
    cn_base: float
    cn_effective: float
    potential_retention_S_mm: float
    initial_abstraction_Ia_mm: float
    scs_runoff_mm: float
    scs_runoff_ratio: float
    amc_class: str
    amc_5day_mm: float
    soil_saturation_theta: float
    imd_24h_class: str
    f_rain: float
    f_twi: float
    f_hand: float
    f_river: float
    f_soil: float
    f_hist: float
    f_pop: float
    fhi: float
    rational_Q_m3s: float
    manning_drainage_index: float
    drainage_deficit_mm: float

    def to_dict(self) -> dict:
        return asdict(self)


def cn_from_population_density(population_density: float) -> Tuple[float, str]:
    """Map population density to TR-55 land-use curve number."""
    if population_density > 45_000:
        return float(CN_BY_LANDUSE["impervious"]), "impervious"
    if population_density > 35_000:
        return float(CN_BY_LANDUSE["industrial"]), "industrial"
    if population_density > 25_000:
        return float(CN_BY_LANDUSE["residential"]), "residential"
    return float(CN_BY_LANDUSE["open_space"]), "open_space"


def amc_adjust_cn(cn_ii: float, antecedent_5day_mm: float) -> Tuple[float, str]:
    """
    Antecedent Moisture Condition adjustment (USDA TR-55 Table 4-1).
    CN_I  = CN_II / (2.281 - 0.01281·CN_II)   AMC-I  (dry, 5d < 35 mm)
    CN_III = CN_II / (0.4036 + 0.00572·CN_II)  AMC-III (wet, 5d > 53 mm)
    """
    cn = float(cn_ii)
    if antecedent_5day_mm < 35.0:
        cn_eff = cn / (2.281 - 0.01281 * cn)
        label = "AMC-I"
    elif antecedent_5day_mm > 53.0:
        cn_eff = cn / (0.4036 + 0.00572 * cn)
        label = "AMC-III"
    else:
        cn_eff = cn
        label = "AMC-II"
    return float(np.clip(cn_eff, 30.0, 99.0)), label


def scs_curve_number_runoff(
    rainfall_24h_mm: float,
    cn_effective: float,
) -> Tuple[float, float, float, float]:
    """
    SCS-CN excess rainfall (TR-55, SI units):
        S  = (25400 / CN) - 254          [mm]
        Ia = 0.2 · S
        Q  = (P - Ia)² / (P + 0.8·S)   if P > Ia, else Q = 0
    Returns: Q_mm, runoff_ratio, S_mm, Ia_mm
    """
    p = float(max(0.0, rainfall_24h_mm))
    cn = float(np.clip(cn_effective, 30.0, 99.0))
    s_mm = (25400.0 / cn) - 254.0
    ia_mm = 0.2 * s_mm
    if p <= ia_mm:
        return 0.0, 0.0, round(s_mm, 4), round(ia_mm, 4)
    q_mm = ((p - ia_mm) ** 2) / (p + 0.8 * s_mm)
    ratio = q_mm / p if p > 0 else 0.0
    return round(q_mm, 4), round(ratio, 6), round(s_mm, 4), round(ia_mm, 4)


def compute_twi(
    river_proximity_km: float,
    elevation_m: float,
    population_density: float,
) -> float:
    """
    Topographic Wetness Index (Beven & Kirkby, 1979):
        TWI = ln(a / tan(β))
    Zone-level proxies when DEM is unavailable:
        a ≈ 10 / (d_river + 0.1)  [km² contributing area proxy]
        β ≈ arctan(|z - z_mean| / 50)  [slope from plateau deviation]
    Urban correction (impervious fraction φ):
        TWI' = TWI · (1 + 0.3·φ),  φ = min(0.9, N_pop / 55000)
    """
    d = max(0.1, float(river_proximity_km))
    a = 10.0 / (d + 0.1)
    slope_deg = max(0.5, abs(float(elevation_m) - BENGALURU_MEAN_ELEVATION_M) / 50.0)
    tan_beta = max(0.01, math.tan(math.radians(slope_deg)))
    twi = math.log(a / tan_beta)
    phi = min(0.9, float(population_density) / 55_000.0)
    return round(max(0.0, twi * (1.0 + 0.3 * phi)), 6)


def compute_hand(elevation_m: float, river_proximity_km: float) -> float:
    """
    Height Above Nearest Drainage (HAND) proxy [m]:
        HAND ≈ (z - z_min) · (1 - exp(-1 / (d_river + 0.05)))
    Lower HAND → closer to drainage → higher flood exposure.
    """
    z_min = BENGALURU_ELEV_RANGE_M[0]
    z = float(elevation_m)
    d = max(0.05, float(river_proximity_km))
    hand = max(0.0, (z - z_min) * (1.0 - math.exp(-1.0 / d)))
    return round(hand, 4)


def soil_saturation_theta(rainfall_7d_mm: float, field_capacity_mm: float = FIELD_CAPACITY_7D_MM) -> float:
    """
    Volumetric saturation index θ ∈ [0, 1]:
        θ = 1 - exp(-P_7d / FC)
    FC = field capacity for Bengaluru urban laterite (default 480 mm / 7d).
    """
    p = max(0.0, float(rainfall_7d_mm))
    fc = max(1.0, float(field_capacity_mm))
    return round(float(1.0 - math.exp(-p / fc)), 6)


def imd_classify_24h(rainfall_24h_mm: float) -> str:
    """IMD 24h accumulated rainfall category."""
    r = float(rainfall_24h_mm)
    for threshold, label in IMD_24H_THRESHOLDS_MM:
        if r >= threshold:
            return label
    return "dry"


def normalize_rainfall_factor(rainfall_24h_mm: float) -> float:
    """Piecewise-linear normalization to [0, 1] using IMD 24h thresholds."""
    r = float(rainfall_24h_mm)
    if r >= 204.4:
        return 1.0
    if r >= 150.0:
        return 0.85 + 0.15 * (r - 150.0) / 54.4
    if r >= 100.0:
        return 0.65 + 0.20 * (r - 100.0) / 50.0
    if r >= 64.5:
        return 0.45 + 0.20 * (r - 64.5) / 35.5
    if r >= 35.5:
        return 0.25 + 0.20 * (r - 35.5) / 29.0
    if r >= 7.5:
        return 0.10 + 0.15 * (r - 7.5) / 28.0
    return max(0.0, r / 75.0)


def normalize_river_factor(river_proximity_km: float) -> float:
    d = float(river_proximity_km)
    if d <= 0.5:
        return 1.0
    if d <= 2.0:
        return 0.75 - 0.25 * (d - 0.5) / 1.5
    if d <= 5.0:
        return 0.50 - 0.25 * (d - 2.0) / 3.0
    return max(0.0, 0.25 - 0.05 * (d - 5.0))


def normalize_hand_factor(hand_m: float) -> float:
    """Inverse HAND: low elevation above drainage → high risk factor."""
    return float(np.clip(1.0 - hand_m / 90.0, 0.0, 1.0))


def rational_method_peak_discharge_m3s(
    rainfall_intensity_mm_hr: float,
    runoff_coefficient: float,
    catchment_area_km2: float,
) -> float:
    """
    Rational formula (Chow et al., 1988):
        Q_p = 0.278 · C · i · A
    i [mm/hr], A [km²], Q [m³/s], C = runoff coefficient (from SCS ratio).
    """
    i = max(0.0, float(rainfall_intensity_mm_hr))
    c = float(np.clip(runoff_coefficient, 0.05, 0.95))
    a = max(0.01, float(catchment_area_km2))
    return round(0.278 * c * i * a, 4)


def manning_drainage_capacity_index(
    drain_slope: float,
    hydraulic_radius_m: float,
    manning_n: float,
) -> float:
    """
    Manning's equation (uniform flow):
        V = (1/n) · R^(2/3) · S^(1/2)
    Returns velocity [m/s] as drainage capacity index (higher = better conveyance).
    Typical urban drain: n=0.013, R=0.25m, S=0.002.
    """
    n = max(0.009, float(manning_n))
    r = max(0.05, float(hydraulic_radius_m))
    s = max(1e-5, float(drain_slope))
    v = (1.0 / n) * (r ** (2.0 / 3.0)) * (s ** 0.5)
    return round(v, 6)


def compute_fhi(
    rainfall_24h_mm: float,
    twi: float,
    hand_m: float,
    river_proximity_km: float,
    soil_theta: float,
    flood_history_freq: float,
    population_density: float,
    runoff_mm: float,
) -> Tuple[float, Dict[str, float]]:
    """
    Flood Hazard Index (AHP-weighted MCDA):
        FHI = Σ w_i · f_i,  then FHI' = min(1, FHI · (1 + 0.25·(Q/P)))
    """
    f_rain = normalize_rainfall_factor(rainfall_24h_mm)
    f_twi = float(np.clip((twi - 3.0) / 12.0, 0.0, 1.0))
    f_hand = normalize_hand_factor(hand_m)
    f_riv = normalize_river_factor(river_proximity_km)
    f_soil = float(np.clip(soil_theta, 0.0, 1.0))
    f_hist = float(np.clip(flood_history_freq, 0.0, 1.0))
    f_pop = float(np.clip(population_density / 55_000.0, 0.0, 1.0))

    w = AHP_WEIGHTS
    fhi = (
        w["rainfall_intensity"] * f_rain
        + w["twi"] * f_twi
        + w["hand"] * f_hand
        + w["river_proximity"] * f_riv
        + w["soil_saturation"] * f_soil
        + w["flood_history"] * f_hist
        + w["population"] * f_pop
    )
    p = max(1.0, float(rainfall_24h_mm))
    runoff_ratio = min(1.0, float(runoff_mm) / p)
    fhi_amp = float(min(1.0, fhi * (1.0 + 0.25 * runoff_ratio)))

    factors = {
        "f_rain": round(f_rain, 6),
        "f_twi": round(f_twi, 6),
        "f_hand": round(f_hand, 6),
        "f_riv": round(f_riv, 6),
        "f_soil": round(f_soil, 6),
        "f_hist": round(f_hist, 6),
        "f_pop": round(f_pop, 6),
    }
    return round(fhi_amp, 6), factors


def fhi_to_risk_class(fhi: float) -> int:
    if fhi >= FHI_CLASS_THRESHOLDS[2]:
        return 3
    if fhi >= FHI_CLASS_THRESHOLDS[1]:
        return 2
    if fhi >= FHI_CLASS_THRESHOLDS[0]:
        return 1
    return 0


def catchment_area_proxy_km2(river_proximity_km: float) -> float:
    """Effective contributing area for Rational method [km²]."""
    return round(max(0.5, 12.0 / (float(river_proximity_km) + 0.5)), 4)


def run_full_hydrology(
    rainfall_24h_mm: float,
    rainfall_7d_mm: float,
    elevation_m: float,
    river_proximity_km: float,
    flood_history_freq: float,
    population_density: float,
    drain_slope: float = 0.002,
    hydraulic_radius_m: float = 0.25,
    manning_n: float = 0.013,
) -> HydrologyTrace:
    """
    Execute full hydrological pipeline; every intermediate value is stored.
  """
    cn_base, _ = cn_from_population_density(population_density)
    amc_5day = float(rainfall_7d_mm) * (5.0 / 7.0)
    cn_eff, amc_label = amc_adjust_cn(cn_base, amc_5day)
    q_mm, q_ratio, s_mm, ia_mm = scs_curve_number_runoff(rainfall_24h_mm, cn_eff)

    twi = compute_twi(river_proximity_km, elevation_m, population_density)
    hand = compute_hand(elevation_m, river_proximity_km)
    theta = soil_saturation_theta(rainfall_7d_mm)
    imd_cls = imd_classify_24h(rainfall_24h_mm)

    fhi, factors = compute_fhi(
        rainfall_24h_mm, twi, hand, river_proximity_km,
        theta, flood_history_freq, population_density, q_mm,
    )

    intensity_mm_hr = rainfall_24h_mm / 24.0 if rainfall_24h_mm > 0 else 0.0
    area_km2 = catchment_area_proxy_km2(river_proximity_km)
    q_peak = rational_method_peak_discharge_m3s(intensity_mm_hr, q_ratio, area_km2)
    v_drain = manning_drainage_capacity_index(drain_slope, hydraulic_radius_m, manning_n)

    # Drainage deficit: runoff depth minus what drains in 24h at Manning velocity (simplified)
    drain_depth_capacity_mm = v_drain * 86_400.0 * 1000.0 / 1e6  # m/s → mm/day capacity proxy
    deficit = max(0.0, q_mm - min(drain_depth_capacity_mm, q_mm * 2.0))

    return HydrologyTrace(
        twi=twi,
        hand_m=hand,
        cn_base=cn_base,
        cn_effective=cn_eff,
        potential_retention_S_mm=s_mm,
        initial_abstraction_Ia_mm=ia_mm,
        scs_runoff_mm=q_mm,
        scs_runoff_ratio=q_ratio,
        amc_class=amc_label,
        amc_5day_mm=round(amc_5day, 3),
        soil_saturation_theta=theta,
        imd_24h_class=imd_cls,
        f_rain=factors["f_rain"],
        f_twi=factors["f_twi"],
        f_hand=factors["f_hand"],
        f_river=factors["f_riv"],
        f_soil=factors["f_soil"],
        f_hist=factors["f_hist"],
        f_pop=factors["f_pop"],
        fhi=fhi,
        rational_Q_m3s=q_peak,
        manning_drainage_index=v_drain,
        drainage_deficit_mm=round(deficit, 4),
    )


def ensemble_risk_class(
    ml_class: Optional[int],
    fhi: float,
    rainfall_24h_mm: float,
    ml_weight: float = 0.55,
) -> Tuple[int, str]:
    """
    Hybrid AHP–ML fusion (cf. Springer Nat. Hazards 2025 AHP-XGBoost):
        score = w_ml · P(ML class) + w_phys · FHI  → discretized to 4 classes
    When ML unavailable, physics-only. When rain < ACTIVE_RAIN_24H_MM, force LOW.
    """
    if rainfall_24h_mm < ACTIVE_RAIN_24H_MM:
        return 0, "physics_dry_rule"

    rc_fhi = fhi_to_risk_class(fhi)
    if ml_class is None:
        return rc_fhi, "physics_only"

    # Weighted class index fusion (transparent, no black box)
    blended = ml_weight * float(ml_class) + (1.0 - ml_weight) * float(rc_fhi)
    if rainfall_24h_mm < 20.0:
        blended = min(blended, float(rc_fhi) + 0.25)  # cap ML optimism in light rain
    rc = int(np.clip(round(blended), 0, 3))
    return rc, "ahp_ml_ensemble"
