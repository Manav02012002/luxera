"""
Luxera Daylight Calculation

Calculates daylight factors and interior illuminance from windows.

Key concepts:
- Daylight Factor (DF): Ratio of indoor to outdoor illuminance (%)
- Sky Component (SC): Direct light from sky through window
- Externally Reflected Component (ERC): Light from external surfaces
- Internally Reflected Component (IRC): Light bouncing inside room

Standards: EN 17037, BS 8206-2
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum, auto

from luxera.geometry.core import Vector3, Room, Polygon


class SkyType(Enum):
    """CIE Standard Sky types."""
    OVERCAST = auto()      # CIE Standard Overcast Sky
    CLEAR = auto()         # CIE Clear Sky
    INTERMEDIATE = auto()  # Partly cloudy


@dataclass
class SkyModel:
    """Sky luminance model parameters."""
    sky_type: SkyType
    zenith_luminance: float = 10000  # cd/m²
    sun_altitude: float = 45  # degrees
    sun_azimuth: float = 180  # degrees (south)
    
    def get_luminance(self, altitude: float, azimuth: float) -> float:
        """Get sky luminance at given direction."""
        if self.sky_type == SkyType.OVERCAST:
            return cie_overcast_sky(altitude, self.zenith_luminance)
        elif self.sky_type == SkyType.CLEAR:
            return cie_clear_sky(
                altitude, azimuth,
                self.sun_altitude, self.sun_azimuth,
                self.zenith_luminance
            )
        return self.zenith_luminance * 0.5


def cie_overcast_sky(altitude_deg: float, Lz: float = 10000) -> float:
    """
    CIE Standard Overcast Sky luminance.
    L = Lz × (1 + 2 sin(γ)) / 3
    """
    gamma = math.radians(max(0, altitude_deg))
    return Lz * (1 + 2 * math.sin(gamma)) / 3


def cie_clear_sky(
    alt: float, azi: float,
    sun_alt: float, sun_azi: float,
    Lz: float = 10000
) -> float:
    """CIE Clear Sky luminance (simplified)."""
    gamma = math.radians(max(0, alt))
    chi = abs(azi - sun_azi)
    if chi > 180:
        chi = 360 - chi
    
    # Angular distance from sun
    sun_gamma = math.radians(sun_alt)
    zeta = math.acos(
        math.sin(gamma) * math.sin(sun_gamma) +
        math.cos(gamma) * math.cos(sun_gamma) * math.cos(math.radians(chi))
    )
    
    # Gradation and scattering
    phi = 1 + math.cos(zeta) ** 2
    f_gamma = 0.91 + 10 * math.exp(-3 * zeta) + 0.45 * math.cos(zeta) ** 2
    
    return Lz * f_gamma * phi / 10


@dataclass
class Window:
    """Window for daylight calculations."""
    name: str
    position: Vector3  # Center of window
    width: float
    height: float
    normal: Vector3  # Outward normal
    sill_height: float = 0.9
    transmittance: float = 0.7
    frame_factor: float = 0.8  # Glass fraction
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    @property
    def glazed_area(self) -> float:
        return self.area * self.frame_factor


@dataclass
class DaylightFactorResult:
    """Daylight factor calculation result."""
    point: Vector3
    daylight_factor: float  # Percentage
    sky_component: float
    external_reflected: float
    internal_reflected: float
    illuminance_overcast: float  # lux at 10,000 lux outdoor
    
    @property
    def total_df(self) -> float:
        return self.daylight_factor
    
    def meets_en17037(self, target_df: float = 2.0) -> bool:
        """Check EN 17037 compliance (minimum 2% DF)."""
        return self.daylight_factor >= target_df


def calculate_sky_illuminance(sky_type: SkyType = SkyType.OVERCAST) -> float:
    """Get standard outdoor illuminance for sky type."""
    if sky_type == SkyType.OVERCAST:
        return 10000  # CIE Standard Overcast
    elif sky_type == SkyType.CLEAR:
        return 50000  # Bright clear day
    return 20000


def _solid_angle_window(
    point: Vector3,
    window: Window
) -> float:
    """Calculate solid angle of window from point."""
    to_window = window.position - point
    dist = to_window.length()
    if dist < 0.1:
        return 0
    
    cos_theta = abs(to_window.normalize().dot(window.normal))
    return (window.glazed_area * cos_theta) / (dist ** 2)


def _sky_component(
    point: Vector3,
    window: Window,
    sky: SkyModel
) -> float:
    """Calculate sky component of daylight factor."""
    to_window = window.position - point
    dist = to_window.length()
    if dist < 0.1:
        return 0
    
    direction = to_window.normalize()
    
    # Check if point can see window
    cos_view = direction.dot(window.normal)
    if cos_view >= 0:  # Window facing away
        return 0
    
    # Altitude angle to window center
    altitude = math.degrees(math.asin(direction.z))
    
    # Sky luminance in window direction
    L_sky = sky.get_luminance(altitude, 0)
    
    # Solid angle
    omega = _solid_angle_window(point, window)
    
    # Sky component
    sc = (L_sky * omega * window.transmittance) / (math.pi * 10000)
    
    return max(0, sc * 100)  # As percentage


def _internal_reflected_component(
    room: Room,
    windows: List[Window],
    point: Vector3
) -> float:
    """Calculate internally reflected component."""
    total_window_area = sum(w.glazed_area for w in windows)
    if total_window_area == 0:
        return 0
    
    floor_area = room.floor_area
    rho_avg = (
        room.floor_material.reflectance * 0.4 +
        room.wall_material.reflectance * 0.4 +
        room.ceiling_material.reflectance * 0.2
    )
    
    # Simplified IRC formula
    irc = 0.85 * total_window_area * rho_avg / (floor_area * (1 - rho_avg ** 2))
    
    return max(0, irc * 100)


def calculate_daylight_factor(
    point: Vector3,
    room: Room,
    windows: List[Window],
    sky: SkyModel = None
) -> DaylightFactorResult:
    """
    Calculate daylight factor at a point.
    
    DF = SC + ERC + IRC
    """
    if sky is None:
        sky = SkyModel(SkyType.OVERCAST)
    
    # Sky component from each window
    sc_total = sum(_sky_component(point, w, sky) for w in windows)
    
    # External reflected (simplified - assume 10% of SC)
    erc = sc_total * 0.1
    
    # Internal reflected
    irc = _internal_reflected_component(room, windows, point)
    
    df = sc_total + erc + irc
    
    # Illuminance at standard overcast sky
    outdoor_illum = calculate_sky_illuminance(sky.sky_type)
    indoor_illum = df * outdoor_illum / 100
    
    return DaylightFactorResult(
        point=point,
        daylight_factor=df,
        sky_component=sc_total,
        external_reflected=erc,
        internal_reflected=irc,
        illuminance_overcast=indoor_illum,
    )


def analyze_room_daylight(
    room: Room,
    windows: List[Window],
    grid_spacing: float = 1.0,
    work_plane_height: float = 0.85
) -> List[DaylightFactorResult]:
    """Calculate daylight factors on a grid."""
    results = []
    bb_min, bb_max = room.get_bounding_box()
    sky = SkyModel(SkyType.OVERCAST)
    
    x = bb_min.x + grid_spacing / 2
    while x < bb_max.x:
        y = bb_min.y + grid_spacing / 2
        while y < bb_max.y:
            point = Vector3(x, y, work_plane_height)
            result = calculate_daylight_factor(point, room, windows, sky)
            results.append(result)
            y += grid_spacing
        x += grid_spacing
    
    return results
