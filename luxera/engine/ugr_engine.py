from __future__ import annotations

from typing import List, Optional

from luxera.calculation.ugr import (
    UGRObserverPosition,
    UGRAnalysis,
    LuminaireForUGR,
    analyze_room_ugr,
)
from luxera.geometry.core import Room, Vector3
from luxera.calculation.illuminance import Luminaire
from luxera.photometry.sample import sample_intensity_cd


def _to_ugr_luminaires(luminaires: List[Luminaire]) -> List[LuminaireForUGR]:
    out: List[LuminaireForUGR] = []
    for lum in luminaires:
        # Use luminous dimensions if available; fall back to conservative default
        width = lum.photometry.luminous_width_m or 0.6
        length = lum.photometry.luminous_length_m or 0.6

        # Luminous intensity in downward direction as a proxy (Type C, gamma=0)
        intensity = sample_intensity_cd(lum.photometry, Vector3(0, 0, -1))
        out.append(
            LuminaireForUGR.from_ies_and_position(
                position=lum.transform.position,
                ies_candela_at_angle=float(intensity * lum.flux_multiplier),
                luminous_width=width,
                luminous_length=length,
            )
        )
    return out


def compute_ugr_default(
    room: Room,
    luminaires: List[Luminaire],
    grid_spacing: float = 2.0,
    eye_heights: Optional[List[float]] = None,
) -> Optional[UGRAnalysis]:
    if not luminaires:
        return None

    ugr_lums = _to_ugr_luminaires(luminaires)
    # Use photometry total flux when available; fall back to luminance-area estimate
    total_flux = 0.0
    for lum, ugr_lum in zip(luminaires, ugr_lums):
        if lum.photometry.luminous_flux_lm is not None:
            total_flux += lum.photometry.luminous_flux_lm * lum.flux_multiplier
        else:
            total_flux += ugr_lum.luminance * ugr_lum.luminous_area * 3.14159

    heights = eye_heights or [1.2, 1.7]
    analyses: List[UGRAnalysis] = []
    for h in heights:
        try:
            analyses.append(
                analyze_room_ugr(
                    room,
                    ugr_lums,
                    total_flux=total_flux,
                    grid_spacing=grid_spacing,
                    eye_height=h,
                )
            )
        except Exception:
            continue

    if not analyses:
        return None

    # Combine results: choose worst-case UGR
    worst = max(analyses, key=lambda a: a.worst_case_ugr)
    return worst
