from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional

from luxera.project.schema import Project


@dataclass(frozen=True)
class LENIInputs:
    """Inputs for EN 15193 LENI calculation."""

    installed_power_W: float
    room_area_m2: float
    annual_operating_hours: float
    daylight_dependent_hours: float
    non_occupied_hours: float
    occupancy_factor: float
    daylight_factor_constant: float
    daylight_factor_supply: float
    absence_factor: float
    parasitic_power_W: float
    emergency_power_W: float
    emergency_hours: float


@dataclass(frozen=True)
class LENIResult:
    leni_kWh_per_m2_year: float
    energy_lighting_kWh: float
    energy_parasitic_kWh: float
    total_energy_kWh: float
    power_density_W_per_m2: float
    normalised_power_pn: float
    breakdown: Dict[str, float]
    compliant: Optional[bool]
    limit_kWh_per_m2_year: Optional[float]


def _clamp_factor(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def compute_leni(inputs: LENIInputs, limit_kWh_per_m2_year: Optional[float] = None) -> LENIResult:
    """
    EN 15193-1:2017 LENI calculation.

    W_L = (P_n * F_C * ((t_O - t_D) * F_O + t_D * F_O * F_D,S * F_D,C + t_N * F_A)) / 1000
    W_P = (P_parasitic * (8760 - t_O)) / 1000 + (P_emergency * t_emergency) / 1000
    LENI = (W_L + W_P) / A
    """
    area = max(float(inputs.room_area_m2), 1e-9)
    p_n = max(float(inputs.installed_power_W), 0.0)
    t_o = max(float(inputs.annual_operating_hours), 0.0)
    t_d = max(0.0, min(float(inputs.daylight_dependent_hours), t_o))
    t_n = max(float(inputs.non_occupied_hours), 0.0)
    f_o = _clamp_factor(inputs.occupancy_factor)
    f_d_c = _clamp_factor(inputs.daylight_factor_constant)
    f_d_s = _clamp_factor(inputs.daylight_factor_supply)
    f_a = _clamp_factor(inputs.absence_factor)
    p_par = max(float(inputs.parasitic_power_W), 0.0)
    p_em = max(float(inputs.emergency_power_W), 0.0)
    t_em = max(float(inputs.emergency_hours), 0.0)
    f_c = 1.0

    daylight_reduction = max(0.0, min(1.0, f_d_s * f_d_c))
    effective_hours = ((t_o - t_d) * f_o) + (t_d * f_o * (1.0 - daylight_reduction)) + (t_n * f_a)
    w_l = (p_n * f_c * effective_hours) / 1000.0
    w_p = (p_par * max(8760.0 - t_o, 0.0)) / 1000.0 + (p_em * t_em) / 1000.0
    total = w_l + w_p
    leni = total / area
    pn = p_n / area
    limit = float(limit_kWh_per_m2_year) if limit_kWh_per_m2_year is not None else None
    compliant = (leni <= limit) if limit is not None else None

    breakdown = {
        "P_n_W": p_n,
        "A_m2": area,
        "t_O_h": t_o,
        "t_D_h": t_d,
        "t_N_h": t_n,
        "F_C": f_c,
        "F_O": f_o,
        "F_D_C": f_d_c,
        "F_D_S": f_d_s,
        "daylight_reduction": daylight_reduction,
        "F_A": f_a,
        "effective_hours_h": effective_hours,
        "W_L_kWh": w_l,
        "W_P_kWh": w_p,
        "W_total_kWh": total,
        "LENI_kWh_per_m2_year": leni,
    }
    return LENIResult(
        leni_kWh_per_m2_year=leni,
        energy_lighting_kWh=w_l,
        energy_parasitic_kWh=w_p,
        total_energy_kWh=total,
        power_density_W_per_m2=pn,
        normalised_power_pn=pn,
        breakdown=breakdown,
        compliant=compliant,
        limit_kWh_per_m2_year=limit,
    )


LENI_PROFILES: Dict[str, LENIInputs] = {
    "office_open_plan": LENIInputs(0, 0, 2500, 1800, 6260, 0.90, 0.90, 0.60, 0.10, 0, 0, 0),
    "office_cellular": LENIInputs(0, 0, 2300, 1650, 6460, 0.88, 0.90, 0.58, 0.12, 0, 0, 0),
    "classroom": LENIInputs(0, 0, 1800, 1300, 6960, 0.92, 0.90, 0.65, 0.10, 0, 0, 0),
    "hospital_ward": LENIInputs(0, 0, 4200, 2400, 4560, 0.96, 0.92, 0.55, 0.08, 0, 0, 0),
    "retail": LENIInputs(0, 0, 3500, 2200, 5260, 0.95, 0.92, 0.50, 0.08, 0, 0, 0),
    "warehouse": LENIInputs(0, 0, 2500, 1200, 6260, 0.78, 0.90, 0.45, 0.18, 0, 0, 0),
    "corridor": LENIInputs(0, 0, 5000, 900, 3760, 0.86, 0.92, 0.30, 0.20, 0, 0, 0),
    "parking_garage": LENIInputs(0, 0, 5500, 700, 3260, 0.80, 0.92, 0.25, 0.25, 0, 0, 0),
    "hotel_room": LENIInputs(0, 0, 1800, 800, 6960, 0.62, 0.90, 0.35, 0.30, 0, 0, 0),
}


LENI_LIMITS_KWH_M2_YEAR: Dict[str, float] = {
    "office_open_plan": 28.0,
    "office_cellular": 26.0,
    "classroom": 22.0,
    "hospital_ward": 42.0,
    "retail": 55.0,
    "warehouse": 18.0,
    "corridor": 20.0,
    "parking_garage": 24.0,
    "hotel_room": 19.0,
}


def _extract_watts(meta: dict) -> float:
    for key in ("watts", "power_w", "input_w", "input_power_w", "rated_power_w"):
        val = meta.get(key)
        if isinstance(val, (int, float)):
            return max(0.0, float(val))
    lumens = meta.get("lumens") or meta.get("luminous_flux_lm")
    efficacy = meta.get("efficacy_lm_per_w")
    if isinstance(lumens, (int, float)) and isinstance(efficacy, (int, float)) and float(efficacy) > 1e-6:
        return max(0.0, float(lumens) / float(efficacy))
    if isinstance(lumens, (int, float)):
        return max(0.0, float(lumens) / 100.0)
    return 0.0


def compute_leni_from_project(project: "Project", profile_name: str = "office_open_plan") -> LENIResult:
    """
    Extract installed power and room area from project, merge with profile defaults, compute LENI.
    """
    profile_key = str(profile_name).strip().lower()
    base = LENI_PROFILES.get(profile_key, LENI_PROFILES["office_open_plan"])
    assets = {str(a.id): a for a in project.photometry_assets}

    installed_power = 0.0
    parasitic = 0.0
    emergency = 0.0
    for lum in project.luminaires:
        asset = assets.get(str(lum.photometry_asset_id))
        meta = dict(getattr(asset, "metadata", {}) or {})
        watts = _extract_watts(meta)
        multiplier = float(getattr(lum, "flux_multiplier", 1.0) or 1.0)
        installed_power += watts * max(multiplier, 0.0)
        standby = meta.get("parasitic_power_w") or meta.get("standby_power_w")
        emer = meta.get("emergency_power_w")
        if isinstance(standby, (int, float)):
            parasitic += max(0.0, float(standby))
        if isinstance(emer, (int, float)):
            emergency += max(0.0, float(emer))

    area = 0.0
    for room in project.geometry.rooms:
        area += max(0.0, float(room.width) * float(room.length))
    if area <= 1e-9 and project.grids:
        g = project.grids[0]
        area = max(0.0, float(g.width) * float(g.height))

    merged = replace(
        base,
        installed_power_W=installed_power,
        room_area_m2=area,
        parasitic_power_W=(parasitic if parasitic > 0.0 else base.parasitic_power_W),
        emergency_power_W=(emergency if emergency > 0.0 else base.emergency_power_W),
    )
    return compute_leni(merged, limit_kWh_per_m2_year=LENI_LIMITS_KWH_M2_YEAR.get(profile_key))
