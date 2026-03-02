from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TunnelGeometry:
    length_m: float
    width_m: float
    height_m: float
    gradient_pct: float
    orientation_deg: float
    speed_limit_kmh: float
    traffic_volume_veh_h: float
    portal_type: str


@dataclass(frozen=True)
class TunnelZone:
    name: str
    start_m: float
    end_m: float
    required_luminance_cd_m2: float
    required_uniformity_U0: float
    required_uniformity_Ul: float
    luminaire_spacing_m: Optional[float]
    luminaire_mounting_height_m: Optional[float]


class TunnelLightingDesign:
    """CIE 88:2004 tunnel lighting calculation."""

    _PORTAL_MULTIPLIERS: Dict[str, float] = {
        "unshielded": 0.055,
        "partially_shielded": 0.035,
        "shielded": 0.025,
    }

    def compute_L20(self, tunnel: TunnelGeometry, sky_luminance_cd_m2: float) -> float:
        """
        L20 = access zone luminance (cd/m²) seen by approaching driver.

        This is a simplified CIE 88 approximation based on portal shielding.
        """
        if sky_luminance_cd_m2 < 0.0:
            raise ValueError("sky luminance must be non-negative")

        portal_factor = self._PORTAL_MULTIPLIERS.get(tunnel.portal_type, 0.035)
        # Small geometry influence: steeper uphill approaches and east/west glare can
        # slightly increase adaptation luminance.
        gradient_factor = 1.0 + max(tunnel.gradient_pct, 0.0) * 0.003
        orientation_factor = 1.03 if 45.0 <= (tunnel.orientation_deg % 180.0) <= 135.0 else 1.0
        return sky_luminance_cd_m2 * portal_factor * gradient_factor * orientation_factor

    def compute_zones(self, tunnel: TunnelGeometry, L20: float) -> List[TunnelZone]:
        """
        Compute threshold, transition, interior, and exit zones.
        """
        if tunnel.length_m <= 0.0:
            return []

        speed_kmh = max(tunnel.speed_limit_kmh, 1.0)
        stopping_m = min(self.stopping_distance(speed_kmh), tunnel.length_m)

        traffic_ratio = min(max(tunnel.traffic_volume_veh_h / 2000.0, 0.0), 1.0)
        k_th = 0.05 + 0.05 * traffic_ratio
        L_th = max(0.3, L20 * k_th)
        L_in = self._interior_luminance(tunnel)

        mounting_height = max(5.0, min(tunnel.height_m * 0.65, tunnel.height_m - 0.5))
        spacing = min(40.0, max(8.0, mounting_height * 2.5))

        threshold_end = stopping_m
        remaining = max(0.0, tunnel.length_m - threshold_end)
        exit_len = min(stopping_m, remaining * 0.2)
        interior_len = min(max(30.0, tunnel.length_m * 0.25), max(0.0, remaining - exit_len))
        transition_len = max(0.0, remaining - interior_len - exit_len)

        zones: List[TunnelZone] = []
        zones.append(
            TunnelZone(
                name="threshold",
                start_m=0.0,
                end_m=threshold_end,
                required_luminance_cd_m2=L_th,
                required_uniformity_U0=0.40,
                required_uniformity_Ul=0.60,
                luminaire_spacing_m=spacing,
                luminaire_mounting_height_m=mounting_height,
            )
        )

        transition_count = 0
        if transition_len >= 30.0:
            transition_count = 3
        elif transition_len >= 10.0:
            transition_count = 2
        elif transition_len > 0.0:
            transition_count = 1

        cursor = threshold_end
        prev_l = L_th
        if transition_count > 0:
            seg_len = transition_len / transition_count
            v_m_s = max(speed_kmh / 3.6, 0.1)
            t_th = max(threshold_end / v_m_s, 0.1)
            t_transition_total = max(transition_len / v_m_s, 0.1)
            for idx in range(transition_count):
                start = cursor
                end = min(tunnel.length_m, cursor + seg_len)
                frac_t = (idx + 1) / transition_count
                t_i = frac_t * t_transition_total
                raw_l = L_th * 1.9 * max(t_i / t_th, 1.0) ** (-1.4)
                step_l = max(L_in, min(prev_l * 0.92, raw_l))
                zones.append(
                    TunnelZone(
                        name=f"transition{idx + 1}",
                        start_m=start,
                        end_m=end,
                        required_luminance_cd_m2=step_l,
                        required_uniformity_U0=0.35,
                        required_uniformity_Ul=0.55,
                        luminaire_spacing_m=spacing * 1.1,
                        luminaire_mounting_height_m=mounting_height,
                    )
                )
                prev_l = step_l
                cursor = end

        interior_start = cursor
        interior_end = min(tunnel.length_m, interior_start + interior_len)
        if interior_end > interior_start:
            zones.append(
                TunnelZone(
                    name="interior",
                    start_m=interior_start,
                    end_m=interior_end,
                    required_luminance_cd_m2=L_in,
                    required_uniformity_U0=0.40,
                    required_uniformity_Ul=0.60,
                    luminaire_spacing_m=min(50.0, spacing * 1.25),
                    luminaire_mounting_height_m=mounting_height,
                )
            )

        if interior_end < tunnel.length_m:
            zones.append(
                TunnelZone(
                    name="exit",
                    start_m=interior_end,
                    end_m=tunnel.length_m,
                    required_luminance_cd_m2=5.0 * L_in,
                    required_uniformity_U0=0.35,
                    required_uniformity_Ul=0.50,
                    luminaire_spacing_m=min(55.0, spacing * 1.35),
                    luminaire_mounting_height_m=mounting_height,
                )
            )

        return zones

    def stopping_distance(self, speed_kmh: float) -> float:
        """
        CIE 88 stopping distance.

        d = v*t_r + v²/(2*a), t_r = 1.5 s, a = 8.0 m/s².
        """
        v = max(speed_kmh, 0.0) / 3.6
        return v * 1.5 + (v * v) / (2.0 * 8.0)

    def check_compliance(self, zones: List[TunnelZone], results: Dict[str, float]) -> Dict[str, bool]:
        """Check computed luminance against zone requirements."""
        compliance: Dict[str, bool] = {}
        for zone in zones:
            measured = results.get(zone.name)
            if measured is None:
                measured = results.get(f"{zone.name}_luminance_cd_m2")
            compliance[zone.name] = measured is not None and measured >= zone.required_luminance_cd_m2

        compliance["overall"] = all(compliance.values()) if compliance else False
        return compliance

    def _interior_luminance(self, tunnel: TunnelGeometry) -> float:
        speed = tunnel.speed_limit_kmh
        if speed <= 40.0:
            base = 2.0
        elif speed <= 60.0:
            base = 3.0
        elif speed <= 80.0:
            base = 5.0
        elif speed <= 100.0:
            base = 7.0
        else:
            base = 9.0

        volume_factor = min(max(tunnel.traffic_volume_veh_h / 1500.0, 0.6), 1.8)
        luminance = base * volume_factor
        return min(20.0, max(1.0, luminance))
