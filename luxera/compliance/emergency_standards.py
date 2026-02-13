from __future__ import annotations

from typing import Dict


_PROFILES: dict[tuple[str, str], dict[str, float]] = {
    ("EN1838", "default"): {
        "route_min_lux": 1.0,
        "route_u0_min": 0.1,
        "open_area_min_lux": 0.5,
        "open_area_u0_min": 0.1,
    },
    ("BS5266", "default"): {
        "route_min_lux": 1.0,
        "route_u0_min": 0.1,
        "open_area_min_lux": 0.5,
        "open_area_u0_min": 0.1,
    },
}


def get_standard_profile(standard: str, category: str = "default") -> Dict[str, float]:
    std = str(standard or "EN1838").upper()
    cat = str(category or "default").lower()
    return dict(_PROFILES.get((std, cat), _PROFILES[("EN1838", "default")]))
