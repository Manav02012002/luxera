from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from luxera.models.photometry import PhotometryHeader
from luxera.models.angles import AngleGrid
from luxera.models.candela import CandelaGrid


@dataclass(frozen=True)
class ParseNote:
    message: str
    line_no: Optional[int] = None


@dataclass
class ParseError(Exception):
    message: str
    line_no: Optional[int] = None
    snippet: Optional[str] = None

    def __str__(self) -> str:
        if self.line_no is None:
            return self.message
        return f"Line {self.line_no}: {self.message}"


@dataclass
class ParsedIES:
    standard_line: Optional[str]
    keywords: Dict[str, List[str]]
    tilt_line: Optional[str]
    tilt_data: Optional[Tuple[List[float], List[float]]]  # (angles_deg, factors)
    photometry: Optional[PhotometryHeader]
    angles: Optional[AngleGrid]
    candela: Optional[CandelaGrid]
    raw_lines: List[str]


_NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _is_number(tok: str) -> bool:
    return bool(_NUM_RE.match(tok))


def _tokenise_numeric_block(lines: List[str], start_idx0: int, count: int) -> Tuple[List[float], int, int, int]:
    """
    Read `count` numeric values starting at lines[start_idx0], continuing across lines.
    Returns: (values, start_line_no, end_line_no, next_idx0)
    where line numbers are 1-indexed inclusive, and next_idx0 is the next unread line index.
    """
    values: List[float] = []
    start_line_no: Optional[int] = None
    end_line_no: Optional[int] = None

    idx0 = start_idx0
    while idx0 < len(lines) and len(values) < count:
        s = lines[idx0].strip()
        if s:
            toks = s.split()
            for t in toks:
                if len(values) >= count:
                    break
                if not _is_number(t):
                    raise ParseError(
                        f"Expected numeric value, got: {t}",
                        line_no=idx0 + 1,
                        snippet=lines[idx0],
                    )
                values.append(float(t))

            if start_line_no is None:
                start_line_no = idx0 + 1
            end_line_no = idx0 + 1

        idx0 += 1

    if len(values) != count:
        raise ParseError(
            f"Expected {count} numeric values but found {len(values)}",
            line_no=(end_line_no or (start_idx0 + 1)),
        )

    assert start_line_no is not None and end_line_no is not None
    return values, start_line_no, end_line_no, idx0


def _parse_photometry_header_from_tokens(tokens: List[str], line_no: int) -> PhotometryHeader:
    if len(tokens) < 10:
        raise ParseError("Photometric header line has fewer than 10 numbers", line_no=line_no)

    def as_int(t: str, name: str) -> int:
        if not _is_number(t):
            raise ParseError(f"Non-numeric value for {name}: {t}", line_no=line_no)
        v = float(t)
        if abs(v - round(v)) > 1e-9:
            raise ParseError(f"Expected integer for {name}, got {t}", line_no=line_no)
        return int(round(v))

    def as_float(t: str, name: str) -> float:
        if not _is_number(t):
            raise ParseError(f"Non-numeric value for {name}: {t}", line_no=line_no)
        return float(t)

    num_lamps = as_int(tokens[0], "num_lamps")
    lumens_per_lamp = as_float(tokens[1], "lumens_per_lamp")
    candela_multiplier = as_float(tokens[2], "candela_multiplier")
    num_vertical_angles = as_int(tokens[3], "num_vertical_angles")
    num_horizontal_angles = as_int(tokens[4], "num_horizontal_angles")
    photometric_type = as_int(tokens[5], "photometric_type")
    units_type = as_int(tokens[6], "units_type")
    width = as_float(tokens[7], "width")
    length = as_float(tokens[8], "length")
    height = as_float(tokens[9], "height")

    if photometric_type not in (1, 2, 3):
        raise ParseError(
            f"Unsupported photometric_type={photometric_type} (expected 1,2,3)",
            line_no=line_no,
        )
    if units_type not in (1, 2):
        raise ParseError(
            f"Unsupported units_type={units_type} (expected 1=feet,2=meters)",
            line_no=line_no,
        )

    if num_lamps < 0:
        raise ParseError("num_lamps must be >= 0", line_no=line_no)
    if lumens_per_lamp < 0:
        raise ParseError("lumens_per_lamp must be >= 0", line_no=line_no)
    if candela_multiplier <= 0:
        raise ParseError("candela_multiplier must be > 0", line_no=line_no)
    if num_vertical_angles <= 0 or num_horizontal_angles <= 0:
        raise ParseError("Angle counts must be > 0", line_no=line_no)

    return PhotometryHeader(
        num_lamps=num_lamps,
        lumens_per_lamp=lumens_per_lamp,
        candela_multiplier=candela_multiplier,
        num_vertical_angles=num_vertical_angles,
        num_horizontal_angles=num_horizontal_angles,
        photometric_type=photometric_type,  # type: ignore[arg-type]
        units_type=units_type,              # type: ignore[arg-type]
        width=width,
        length=length,
        height=height,
        line_no=line_no,
    )


def _find_photometry_header_line(lines: List[str], start_idx0: int = 0) -> Optional[Tuple[int, List[str]]]:
    for idx0 in range(start_idx0, len(lines)):
        s = lines[idx0].strip()
        if not s:
            continue
        toks = s.split()
        if len(toks) >= 10 and all(_is_number(t) for t in toks[:10]):
            return idx0, toks
    return None


def _is_strictly_increasing(a: List[float]) -> bool:
    return all(a[i] < a[i + 1] for i in range(len(a) - 1))


def _parse_angles_after_photometry(
    lines: List[str], photometry_idx0: int, ph: PhotometryHeader
) -> Tuple[AngleGrid, int]:
    """
    Parses vertical + horizontal angles after photometry header.
    Returns (AngleGrid, next_idx0) where next_idx0 is where candela data starts.
    """
    idx0 = photometry_idx0 + 1

    v, v_start, v_end, next_idx0 = _tokenise_numeric_block(lines, idx0, ph.num_vertical_angles)
    idx0 = next_idx0

    h, h_start, h_end, next_idx0 = _tokenise_numeric_block(lines, idx0, ph.num_horizontal_angles)
    idx0 = next_idx0

    if not _is_strictly_increasing(v):
        raise ParseError("Vertical angles are not strictly increasing", line_no=v_start)
    if not _is_strictly_increasing(h):
        raise ParseError("Horizontal angles are not strictly increasing", line_no=h_start)

    return (
        AngleGrid(
            vertical_deg=v,
            horizontal_deg=h,
            vertical_line_span=(v_start, v_end),
            horizontal_line_span=(h_start, h_end),
        ),
        idx0,
    )


def _parse_candela_table(
    lines: List[str],
    start_idx0: int,
    ph: PhotometryHeader,
    angles: AngleGrid,
) -> CandelaGrid:
    """
    Candela values are provided as H rows, each containing V values.
    Values may wrap across lines; treat it as one long numeric stream of H*V values,
    then reshape into [H][V] by horizontal-major order.
    """
    H = len(angles.horizontal_deg)
    V = len(angles.vertical_deg)
    total = H * V

    flat, start_ln, end_ln, next_idx0 = _tokenise_numeric_block(lines, start_idx0, total)

    # reshape: first V entries -> row 0 (horizontal angle 0), next V -> row 1, etc.
    values_cd: List[List[float]] = []
    for i in range(H):
        row = flat[i * V : (i + 1) * V]
        values_cd.append(row)

    # scaled
    m = ph.candela_multiplier
    values_cd_scaled: List[List[float]] = [[m * x for x in row] for row in values_cd]

    # stats/flags
    all_vals = [x for row in values_cd_scaled for x in row]
    has_nan_or_inf = any((math.isnan(x) or math.isinf(x)) for x in all_vals)
    has_negative = any(x < 0 for x in all_vals)
    min_cd = min(all_vals) if all_vals else 0.0
    max_cd = max(all_vals) if all_vals else 0.0

    return CandelaGrid(
        values_cd=values_cd,
        values_cd_scaled=values_cd_scaled,
        line_span=(start_ln, end_ln),
        min_cd=min_cd,
        max_cd=max_cd,
        has_negative=has_negative,
        has_nan_or_inf=has_nan_or_inf,
    )


def parse_ies_text(text: str) -> ParsedIES:
    if not text.strip():
        raise ParseError("Empty file")

    raw_lines = text.splitlines()
    lines = [ln.rstrip("\r\n") for ln in raw_lines]

    standard_line: Optional[str] = None
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines):
        head = lines[i].strip()
        if head.upper().startswith("IESNA:LM-63"):
            standard_line = head

    keywords: Dict[str, List[str]] = {}
    tilt_line: Optional[str] = None
    tilt_data: Optional[Tuple[List[float], List[float]]] = None
    tilt_end_idx0: Optional[int] = None

    for ln_idx0, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue

        if s.startswith("[") and "]" in s:
            end = s.find("]")
            key = s[1:end].strip()
            val = s[end + 1 :].strip()
            if key:
                keywords.setdefault(key, []).append(val)
            continue

        if s.upper().startswith("TILT="):
            tilt_line = s
            tilt_type = s.split("=", 1)[1].strip().upper()
            if tilt_type == "INCLUDE":
                # Parse tilt data immediately after this line.
                # Format: N tilt angles, then N multiplying factors.
                # Treat as a numeric stream for robustness.
                # N is the first numeric value after TILT=INCLUDE.
                vals, _, _, next_idx0 = _tokenise_numeric_block(lines, ln_idx0 + 1, 1)
                n = int(round(vals[0]))
                if n <= 0:
                    raise ParseError("Invalid TILT=INCLUDE count", line_no=ln_idx0 + 1)
                angles, _, _, next_idx0 = _tokenise_numeric_block(lines, next_idx0, n)
                factors, _, _, next_idx0 = _tokenise_numeric_block(lines, next_idx0, n)
                tilt_data = (angles, factors)
                tilt_end_idx0 = next_idx0
            continue

    photometry: Optional[PhotometryHeader] = None
    angles: Optional[AngleGrid] = None
    candela: Optional[CandelaGrid] = None

    start_idx0 = tilt_end_idx0 or 0
    found = _find_photometry_header_line(lines, start_idx0=start_idx0)
    if found is not None:
        photometry_idx0, toks = found
        photometry = _parse_photometry_header_from_tokens(toks, line_no=photometry_idx0 + 1)

        angles, next_idx0 = _parse_angles_after_photometry(lines, photometry_idx0, photometry)
        candela = _parse_candela_table(lines, next_idx0, photometry, angles)

    return ParsedIES(
        standard_line=standard_line,
        keywords=keywords,
        tilt_line=tilt_line,
        tilt_data=tilt_data,
        photometry=photometry,
        angles=angles,
        candela=candela,
        raw_lines=lines,
    )
