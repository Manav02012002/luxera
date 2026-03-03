from __future__ import annotations

from typing import Any, Dict


EXTERIOR_CLASSES: Dict[str, Dict[str, Any]] = {
    "parking_general": {"E_avg": 5, "E_min": 1, "description": "General parking areas"},
    "parking_intensive": {"E_avg": 10, "E_min": 3, "description": "Intensive use parking"},
    "pedestrian_walkway": {"E_avg": 5, "E_min": 1, "description": "Pedestrian zones"},
    "loading_bay": {"E_avg": 20, "E_min": 10, "description": "Loading/unloading areas"},
    "storage_yard": {"E_avg": 20, "E_min": 5, "description": "Storage areas"},
    "petrol_station": {"E_avg": 50, "E_min": 20, "description": "Service stations"},
    "building_entrance": {"E_avg": 50, "E_min": 25, "description": "Building entrances"},
    "security_perimeter": {"E_avg": 20, "E_min": 5, "E_v_min": 5, "description": "Security areas"},
    "residential_street": {"E_avg": 3, "E_min": 0.6, "description": "Residential outdoor areas"},
    "bus_stop": {"E_avg": 20, "E_min": 5, "description": "Public transport stops"},
}


def check_exterior_compliance(results: Dict, area_class: str) -> Dict[str, bool]:
    """Check results against EN 12464-2 requirements for the given class."""

    req = EXTERIOR_CLASSES.get(str(area_class))
    if req is None:
        raise ValueError(f"Unknown exterior class: {area_class}")

    e_avg = float(results.get("E_avg", 0.0) or 0.0)
    e_min = float(results.get("E_min", 0.0) or 0.0)
    e_v_min = float(results.get("E_v_min", results.get("E_min", 0.0)) or 0.0)

    checks: Dict[str, bool] = {
        "E_avg": e_avg >= float(req.get("E_avg", 0.0)),
        "E_min": e_min >= float(req.get("E_min", 0.0)),
    }
    if "E_v_min" in req:
        checks["E_v_min"] = e_v_min >= float(req["E_v_min"])

    checks["compliant"] = all(checks.values())
    return checks
