from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class MaintenanceFactorComponents:
    llmf: float
    lsf: float
    lmf: float
    rsf: float

    @property
    def mf(self) -> float:
        return float(self.llmf) * float(self.lsf) * float(self.lmf) * float(self.rsf)


@dataclass(frozen=True)
class MaintenanceSchedule:
    """Defines maintenance intervals and factors over time."""

    lamp_type: str
    rated_life_hours: float
    planned_replacement_hours: float
    environment: str
    cleaning_interval_years: float
    ip_rating: str


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _interp(x: float, table: list[tuple[float, float]]) -> float:
    pts = sorted((float(a), float(b)) for a, b in table)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return y0 + t * (y1 - y0)
    return pts[-1][1]


_LLMF_TABLES: Dict[str, list[tuple[float, float]]] = {
    "led": [(0, 1.00), (10000, 0.98), (25000, 0.96), (50000, 0.93), (70000, 0.88)],
    "fluorescent_t5": [(2000, 0.98), (4000, 0.95), (8000, 0.92), (12000, 0.90), (16000, 0.88)],
    "fluorescent_t8": [(2000, 0.97), (4000, 0.93), (8000, 0.89), (12000, 0.85), (16000, 0.82)],
    "metal_halide": [(2000, 0.85), (6000, 0.75), (9000, 0.70), (12000, 0.65)],
    "hps": [(4000, 0.96), (8000, 0.93), (12000, 0.90), (16000, 0.87)],
}

_LSF_TABLES: Dict[str, list[tuple[float, float]]] = {
    "led": [(0, 1.00), (25000, 0.995), (50000, 0.99), (70000, 0.97)],
    "fluorescent_t5": [(2000, 0.995), (8000, 0.97), (12000, 0.95), (16000, 0.90)],
    "fluorescent_t8": [(2000, 0.99), (8000, 0.96), (12000, 0.93), (16000, 0.88)],
    "metal_halide": [(2000, 0.95), (6000, 0.90), (9000, 0.85), (12000, 0.78)],
    "hps": [(4000, 0.98), (8000, 0.95), (12000, 0.92), (16000, 0.87)],
}

_LMF_TABLE: Dict[str, Dict[str, Dict[int, float]]] = {
    "ip20": {
        "clean": {1: 0.96, 2: 0.93, 3: 0.90},
        "normal": {1: 0.90, 2: 0.84, 3: 0.78},
        "dirty": {1: 0.84, 2: 0.77, 3: 0.72},
        "very_dirty": {1: 0.76, 2: 0.69, 3: 0.62},
    },
    "ip54": {
        "clean": {1: 0.96, 2: 0.93, 3: 0.90},
        "normal": {1: 0.93, 2: 0.89, 3: 0.85},
        "dirty": {1: 0.90, 2: 0.84, 3: 0.79},
        "very_dirty": {1: 0.84, 2: 0.78, 3: 0.72},
    },
    "ip65": {
        "clean": {1: 0.97, 2: 0.95, 3: 0.93},
        "normal": {1: 0.95, 2: 0.92, 3: 0.89},
        "dirty": {1: 0.93, 2: 0.89, 3: 0.85},
        "very_dirty": {1: 0.89, 2: 0.84, 3: 0.79},
    },
}

_RSF_TABLE: Dict[str, Dict[int, float]] = {
    "clean": {1: 0.98, 2: 0.96, 3: 0.94},
    "normal": {1: 0.95, 2: 0.92, 3: 0.89},
    "dirty": {1: 0.90, 2: 0.86, 3: 0.83},
    "very_dirty": {1: 0.86, 2: 0.82, 3: 0.78},
}


def _interp_interval(mapping: Dict[int, float], interval_years: float) -> float:
    return _interp(float(interval_years), [(float(k), float(v)) for k, v in mapping.items()])


def compute_maintenance_factors(schedule: MaintenanceSchedule) -> MaintenanceFactorComponents:
    lamp_type = str(schedule.lamp_type).strip().lower()
    env = str(schedule.environment).strip().lower()
    ip = str(schedule.ip_rating).strip().lower()
    planned_h = max(0.0, float(schedule.planned_replacement_hours))

    llmf_table = _LLMF_TABLES.get(lamp_type, _LLMF_TABLES["led"])
    lsf_table = _LSF_TABLES.get(lamp_type, _LSF_TABLES["led"])
    llmf = _clamp01(_interp(planned_h, llmf_table))
    lsf = _clamp01(_interp(planned_h, lsf_table))

    ip_table = _LMF_TABLE.get(ip, _LMF_TABLE["ip20"])
    env_table = ip_table.get(env, ip_table["normal"])
    lmf = _clamp01(_interp_interval(env_table, float(schedule.cleaning_interval_years)))

    rsf_env = _RSF_TABLE.get(env, _RSF_TABLE["normal"])
    rsf = _clamp01(_interp_interval(rsf_env, float(schedule.cleaning_interval_years)))

    return MaintenanceFactorComponents(llmf=llmf, lsf=lsf, lmf=lmf, rsf=rsf)


MAINTENANCE_PROFILES: Dict[str, MaintenanceSchedule] = {
    "led_office_clean": MaintenanceSchedule("LED", 50000, 50000, "clean", 1.0, "IP20"),
    "led_office_normal": MaintenanceSchedule("LED", 50000, 50000, "normal", 2.0, "IP20"),
    "led_industrial_dirty": MaintenanceSchedule("LED", 50000, 40000, "dirty", 1.0, "IP65"),
    "t5_office": MaintenanceSchedule("fluorescent_T5", 16000, 12000, "normal", 2.0, "IP20"),
    "t8_school": MaintenanceSchedule("fluorescent_T8", 16000, 12000, "normal", 2.0, "IP20"),
    "metal_halide_warehouse": MaintenanceSchedule("metal_halide", 12000, 6000, "dirty", 1.0, "IP54"),
    "hps_roadway": MaintenanceSchedule("HPS", 16000, 12000, "dirty", 2.0, "IP65"),
    "led_parking_garage": MaintenanceSchedule("LED", 50000, 45000, "very_dirty", 1.0, "IP65"),
    "led_hospital_clean": MaintenanceSchedule("LED", 50000, 50000, "clean", 1.0, "IP54"),
}
