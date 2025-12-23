"""
EULUMDAT (.ldt) Parser for Luxera

EULUMDAT is the European standard photometric file format, widely used
alongside IES in the lighting industry. This parser implements the
EULUMDAT format specification.

Format structure (fixed line positions):
- Line 1: Company identification
- Line 2: Type indicator (1-4)
- Line 3: Symmetry indicator (0-4)
- Line 4: Number of C-planes (Mc)
- Line 5: Distance between C-planes (Dc)
- Line 6: Number of luminous intensities per C-plane (Ng)
- Line 7: Distance between luminous intensities (Dg)
- Line 8: Measurement report number
- Line 9: Luminaire name
- Line 10: Luminaire number
- Line 11: File name
- Line 12: Date/user
- Line 13: Length/diameter of luminaire (mm)
- Line 14: Width of luminaire (mm), 0 for circular
- Line 15: Height of luminaire (mm)
- Line 16: Length/diameter of luminous area (mm)
- Line 17: Width of luminous area (mm), 0 for circular
- Line 18: Height of luminous area C0 (mm)
- Line 19: Height of luminous area C90 (mm)
- Line 20: Height of luminous area C180 (mm)
- Line 21: Height of luminous area C270 (mm)
- Line 22: Downward flux fraction (DFF) %
- Line 23: Light output ratio luminaire (LORL) %
- Line 24: Conversion factor for luminous intensities
- Line 25: Tilt of luminaire during measurement
- Line 26: Number of lamp sets (n)
- Lines 26+1 to 26+6n: Lamp data (6 lines per lamp set)
- Lines 26+6n+1 to 26+6n+10: Direct ratios DR (10 values)
- Following lines: C-plane angles (Mc values)
- Following lines: G angles (Ng values)  
- Following lines: Luminous intensity values (Mc × Ng values)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Literal
import math


@dataclass
class LDTParseError(Exception):
    message: str
    line_no: Optional[int] = None

    def __str__(self) -> str:
        if self.line_no is None:
            return self.message
        return f"Line {self.line_no}: {self.message}"


@dataclass(frozen=True)
class LDTLampData:
    """Data for a single lamp set in EULUMDAT file."""
    num_lamps: int
    lamp_type: str
    total_flux: float  # lumens
    color_temperature: str
    color_rendering: str
    wattage: float


@dataclass(frozen=True)
class LDTGeometry:
    """Luminaire geometry from EULUMDAT file."""
    length_mm: float
    width_mm: float  # 0 for circular
    height_mm: float
    luminous_length_mm: float
    luminous_width_mm: float  # 0 for circular
    luminous_height_c0_mm: float
    luminous_height_c90_mm: float
    luminous_height_c180_mm: float
    luminous_height_c270_mm: float
    
    @property
    def is_circular(self) -> bool:
        return self.width_mm == 0


@dataclass(frozen=True)
class LDTHeader:
    """Header information from EULUMDAT file."""
    company: str
    type_indicator: Literal[1, 2, 3, 4]  # 1=point, 2=linear, 3=area
    symmetry: Literal[0, 1, 2, 3, 4]  # 0=none, 1=C0, 2=C0-180, 3=C90-270, 4=all
    num_c_planes: int
    c_plane_spacing: float  # degrees
    num_g_angles: int
    g_angle_spacing: float  # degrees
    report_number: str
    luminaire_name: str
    luminaire_number: str
    filename: str
    date_user: str
    geometry: LDTGeometry
    dff_percent: float  # downward flux fraction
    lorl_percent: float  # light output ratio luminaire
    conversion_factor: float
    tilt_degrees: float
    lamp_sets: List[LDTLampData]
    direct_ratios: List[float]  # 10 values


@dataclass(frozen=True)
class LDTAngles:
    """Angle grids from EULUMDAT file."""
    c_planes_deg: List[float]  # horizontal/C angles
    g_angles_deg: List[float]  # vertical/gamma angles


@dataclass(frozen=True)
class LDTCandela:
    """Candela distribution from EULUMDAT file."""
    # Shape: [num_c_planes][num_g_angles]
    values_cd: List[List[float]]
    values_cd_scaled: List[List[float]]  # multiplied by conversion factor
    min_cd: float
    max_cd: float


@dataclass
class ParsedLDT:
    """Complete parsed EULUMDAT file."""
    header: LDTHeader
    angles: LDTAngles
    candela: LDTCandela
    raw_lines: List[str]


def _safe_float(s: str, line_no: int, field: str) -> float:
    """Parse float with error context."""
    try:
        return float(s.strip().replace(',', '.'))
    except ValueError:
        raise LDTParseError(f"Invalid float for {field}: '{s}'", line_no)


def _safe_int(s: str, line_no: int, field: str) -> int:
    """Parse integer with error context."""
    try:
        return int(float(s.strip().replace(',', '.')))
    except ValueError:
        raise LDTParseError(f"Invalid integer for {field}: '{s}'", line_no)


def _get_line(lines: List[str], idx: int) -> str:
    """Get line at index, raising error if out of bounds."""
    if idx >= len(lines):
        raise LDTParseError(f"Unexpected end of file at line {idx + 1}")
    return lines[idx].strip()


def parse_ldt_text(text: str) -> ParsedLDT:
    """
    Parse EULUMDAT (.ldt) text content.
    
    Args:
        text: Raw text content of .ldt file
        
    Returns:
        ParsedLDT with header, angles, and candela data
        
    Raises:
        LDTParseError: If file format is invalid
    """
    if not text.strip():
        raise LDTParseError("Empty file")
    
    raw_lines = text.splitlines()
    lines = [ln.rstrip('\r\n') for ln in raw_lines]
    
    if len(lines) < 26:
        raise LDTParseError("File too short - EULUMDAT requires at least 26 lines")
    
    # Parse fixed header lines (1-indexed in spec, 0-indexed here)
    company = _get_line(lines, 0)
    type_indicator = _safe_int(_get_line(lines, 1), 2, "type_indicator")
    if type_indicator not in (1, 2, 3, 4):
        raise LDTParseError(f"Invalid type indicator: {type_indicator} (expected 1-4)", 2)
    
    symmetry = _safe_int(_get_line(lines, 2), 3, "symmetry")
    if symmetry not in (0, 1, 2, 3, 4):
        raise LDTParseError(f"Invalid symmetry: {symmetry} (expected 0-4)", 3)
    
    num_c_planes = _safe_int(_get_line(lines, 3), 4, "num_c_planes")
    c_plane_spacing = _safe_float(_get_line(lines, 4), 5, "c_plane_spacing")
    num_g_angles = _safe_int(_get_line(lines, 5), 6, "num_g_angles")
    g_angle_spacing = _safe_float(_get_line(lines, 6), 7, "g_angle_spacing")
    
    report_number = _get_line(lines, 7)
    luminaire_name = _get_line(lines, 8)
    luminaire_number = _get_line(lines, 9)
    filename = _get_line(lines, 10)
    date_user = _get_line(lines, 11)
    
    # Geometry (lines 13-22, indices 12-21)
    length_mm = _safe_float(_get_line(lines, 12), 13, "length")
    width_mm = _safe_float(_get_line(lines, 13), 14, "width")
    height_mm = _safe_float(_get_line(lines, 14), 15, "height")
    lum_length = _safe_float(_get_line(lines, 15), 16, "luminous_length")
    lum_width = _safe_float(_get_line(lines, 16), 17, "luminous_width")
    lum_h_c0 = _safe_float(_get_line(lines, 17), 18, "luminous_height_c0")
    lum_h_c90 = _safe_float(_get_line(lines, 18), 19, "luminous_height_c90")
    lum_h_c180 = _safe_float(_get_line(lines, 19), 20, "luminous_height_c180")
    lum_h_c270 = _safe_float(_get_line(lines, 20), 21, "luminous_height_c270")
    
    geometry = LDTGeometry(
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        luminous_length_mm=lum_length,
        luminous_width_mm=lum_width,
        luminous_height_c0_mm=lum_h_c0,
        luminous_height_c90_mm=lum_h_c90,
        luminous_height_c180_mm=lum_h_c180,
        luminous_height_c270_mm=lum_h_c270,
    )
    
    # Flux and conversion (lines 22-25, indices 21-24)
    dff_percent = _safe_float(_get_line(lines, 21), 22, "dff_percent")
    lorl_percent = _safe_float(_get_line(lines, 22), 23, "lorl_percent")
    conversion_factor = _safe_float(_get_line(lines, 23), 24, "conversion_factor")
    tilt_degrees = _safe_float(_get_line(lines, 24), 25, "tilt")
    
    # Number of lamp sets (line 26, index 25)
    num_lamp_sets = _safe_int(_get_line(lines, 25), 26, "num_lamp_sets")
    
    # Parse lamp data (6 lines per lamp set)
    lamp_sets: List[LDTLampData] = []
    idx = 26
    for i in range(num_lamp_sets):
        if idx + 5 >= len(lines):
            raise LDTParseError(f"Unexpected end of file reading lamp set {i + 1}")
        
        num_lamps = _safe_int(_get_line(lines, idx), idx + 1, f"lamp_set_{i}_num")
        lamp_type = _get_line(lines, idx + 1)
        total_flux = _safe_float(_get_line(lines, idx + 2), idx + 3, f"lamp_set_{i}_flux")
        color_temp = _get_line(lines, idx + 3)
        cri = _get_line(lines, idx + 4)
        wattage = _safe_float(_get_line(lines, idx + 5), idx + 6, f"lamp_set_{i}_wattage")
        
        lamp_sets.append(LDTLampData(
            num_lamps=num_lamps,
            lamp_type=lamp_type,
            total_flux=total_flux,
            color_temperature=color_temp,
            color_rendering=cri,
            wattage=wattage,
        ))
        idx += 6
    
    # Direct ratios (10 values, one per line)
    direct_ratios: List[float] = []
    for i in range(10):
        if idx >= len(lines):
            raise LDTParseError(f"Unexpected end of file reading direct ratio {i + 1}")
        direct_ratios.append(_safe_float(_get_line(lines, idx), idx + 1, f"direct_ratio_{i}"))
        idx += 1
    
    # C-plane angles (num_c_planes values)
    c_planes: List[float] = []
    for i in range(num_c_planes):
        if idx >= len(lines):
            raise LDTParseError(f"Unexpected end of file reading C-plane angle {i + 1}")
        c_planes.append(_safe_float(_get_line(lines, idx), idx + 1, f"c_plane_{i}"))
        idx += 1
    
    # G angles (num_g_angles values)
    g_angles: List[float] = []
    for i in range(num_g_angles):
        if idx >= len(lines):
            raise LDTParseError(f"Unexpected end of file reading G angle {i + 1}")
        g_angles.append(_safe_float(_get_line(lines, idx), idx + 1, f"g_angle_{i}"))
        idx += 1
    
    angles = LDTAngles(c_planes_deg=c_planes, g_angles_deg=g_angles)
    
    # Candela values: num_c_planes × num_g_angles values
    # Stored as num_c_planes blocks of num_g_angles values each
    total_values = num_c_planes * num_g_angles
    flat_values: List[float] = []
    
    while len(flat_values) < total_values and idx < len(lines):
        line = _get_line(lines, idx)
        if line:
            # Handle space or comma separated values on same line
            parts = line.replace(',', ' ').split()
            for p in parts:
                if len(flat_values) >= total_values:
                    break
                flat_values.append(_safe_float(p, idx + 1, "candela"))
        idx += 1
    
    if len(flat_values) != total_values:
        raise LDTParseError(
            f"Expected {total_values} candela values, got {len(flat_values)}"
        )
    
    # Reshape into [C][G] matrix
    values_cd: List[List[float]] = []
    for c in range(num_c_planes):
        row = flat_values[c * num_g_angles : (c + 1) * num_g_angles]
        values_cd.append(row)
    
    # Apply conversion factor
    cf = conversion_factor
    values_cd_scaled = [[cf * v for v in row] for row in values_cd]
    
    all_scaled = [v for row in values_cd_scaled for v in row]
    min_cd = min(all_scaled) if all_scaled else 0.0
    max_cd = max(all_scaled) if all_scaled else 0.0
    
    candela = LDTCandela(
        values_cd=values_cd,
        values_cd_scaled=values_cd_scaled,
        min_cd=min_cd,
        max_cd=max_cd,
    )
    
    header = LDTHeader(
        company=company,
        type_indicator=type_indicator,  # type: ignore
        symmetry=symmetry,  # type: ignore
        num_c_planes=num_c_planes,
        c_plane_spacing=c_plane_spacing,
        num_g_angles=num_g_angles,
        g_angle_spacing=g_angle_spacing,
        report_number=report_number,
        luminaire_name=luminaire_name,
        luminaire_number=luminaire_number,
        filename=filename,
        date_user=date_user,
        geometry=geometry,
        dff_percent=dff_percent,
        lorl_percent=lorl_percent,
        conversion_factor=conversion_factor,
        tilt_degrees=tilt_degrees,
        lamp_sets=lamp_sets,
        direct_ratios=direct_ratios,
    )
    
    return ParsedLDT(
        header=header,
        angles=angles,
        candela=candela,
        raw_lines=lines,
    )
