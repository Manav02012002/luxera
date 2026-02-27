from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from luxera.models.photometry import PhotometryHeader
from luxera.models.angles import AngleGrid
from luxera.models.candela import CandelaGrid
from luxera.parser.tilt_file import TiltFileError, load_tilt_file_payload


@dataclass(frozen=True)
class ParseNote:
    message: str
    line_no: Optional[int] = None


@dataclass(frozen=True)
class ParseWarning:
    code: str
    message: str
    line_no: Optional[int] = None


@dataclass(frozen=True)
class IESMetadata:
    luminous_width_m: Optional[float] = None
    luminous_length_m: Optional[float] = None
    luminous_height_m: Optional[float] = None
    luminous_dimensions_source_unit: Optional[str] = None
    lumens: Optional[float] = None
    cct_k: Optional[float] = None
    cri: Optional[float] = None
    distribution_type: Optional[str] = None
    coordinate_system: Optional[str] = None


@dataclass
class ParseError(Exception):
    message: str
    line_no: Optional[int] = None
    snippet: Optional[str] = None
    filename: Optional[str] = None

    def __str__(self) -> str:
        prefix = f"{self.filename}: " if self.filename else ""
        if self.line_no is None:
            return f"{prefix}{self.message}"
        return f"{prefix}Line {self.line_no}: {self.message}"


@dataclass
class ParsedIES:
    standard_line: Optional[str]
    keywords: Dict[str, List[str]]
    tilt_line: Optional[str]
    tilt_mode: Optional[str]
    tilt_file_path: Optional[str]
    tilt_lamp_to_luminaire_geometry: Optional[str]
    tilt_data: Optional[Tuple[List[float], List[float]]]  # (angles_deg, factors)
    photometry: Optional[PhotometryHeader]
    angles: Optional[AngleGrid]
    candela: Optional[CandelaGrid]
    metadata: IESMetadata
    raw_lines: List[str]
    warnings: List[ParseWarning]


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
            line_token_idx = 0
            for t in toks:
                if len(values) >= count:
                    break
                line_token_idx += 1
                # Allow trailing comments in numeric blocks.
                if t in {";", "#", "!"} or t.startswith(";") or t.startswith("#") or t.startswith("!") or t.startswith("//"):
                    break
                if not _is_number(t):
                    raise ParseError(
                        (
                            f"Expected numeric value #{len(values) + 1} of {count}, got '{t}' "
                            f"(token {line_token_idx} on line)"
                        ),
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
            f"Expected {count} numeric values but found {len(values)} in numeric block",
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


def parse_ies_text(text: str, source_path: str | Path | None = None) -> ParsedIES:
    src = Path(source_path).expanduser().resolve() if source_path is not None else None
    try:
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
        tilt_mode: Optional[str] = None
        tilt_file_path: Optional[str] = None
        tilt_lamp_to_luminaire_geometry: Optional[str] = None
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
                tilt_type = s.split("=", 1)[1].strip()
                tilt_type_u = tilt_type.upper()
                tilt_mode = tilt_type_u.split()[0] if tilt_type_u else None
                if tilt_type_u.startswith("FILE"):
                    toks = tilt_type.split(maxsplit=1)
                    tilt_file_path = toks[1].strip() if len(toks) > 1 else None
                    if src is not None and tilt_file_path:
                        resolved = (src.parent / tilt_file_path).resolve()
                        tilt_file_path = str(resolved)
                        try:
                            payload = load_tilt_file_payload(resolved)
                            tilt_data = (payload.data.angles_deg, payload.data.factors)
                            tilt_lamp_to_luminaire_geometry = payload.geometry_factor
                        except TiltFileError:
                            # Parsing keeps FILE reference even when target is missing/invalid.
                            # Validation layer decides pass/fail status.
                            pass
                    continue
                if tilt_type_u == "INCLUDE":
                    # Parse tilt data immediately after this line.
                    # Format variants:
                    # 1) <lamp_to_luminaire_geometry>, n, angles, multipliers
                    # 2) n, angles, multipliers (legacy compact)
                    idx = ln_idx0 + 1
                    while idx < len(lines) and not lines[idx].strip():
                        idx += 1
                    if idx >= len(lines):
                        raise ParseError("Missing TILT=INCLUDE payload", line_no=ln_idx0 + 1)
                    head = lines[idx].strip()
                    head_tokens = head.split()
                    head_tok = head_tokens[0] if head_tokens else ""
                    # Ambiguous case: a single numeric line can be either geometry token or n.
                    # If next non-empty line is also a single numeric token, treat current as geometry.
                    assume_geometry = not _is_number(head_tok)
                    if not assume_geometry and len(head_tokens) == 1:
                        j = idx + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines):
                            nxt = lines[j].strip().split()
                            if len(nxt) == 1 and _is_number(nxt[0]):
                                assume_geometry = True
                    if assume_geometry:
                        tilt_lamp_to_luminaire_geometry = head
                        idx += 1
                    vals, _, _, next_idx0 = _tokenise_numeric_block(lines, idx, 1)
                    n = int(round(vals[0]))
                    if n <= 0:
                        raise ParseError("Invalid TILT=INCLUDE count", line_no=idx + 1)
                    angles, _, _, next_idx0 = _tokenise_numeric_block(lines, next_idx0, n)
                    factors, _, _, next_idx0 = _tokenise_numeric_block(lines, next_idx0, n)
                    tilt_data = (angles, factors)
                    tilt_end_idx0 = next_idx0
                continue

        photometry: Optional[PhotometryHeader] = None
        angles: Optional[AngleGrid] = None
        candela: Optional[CandelaGrid] = None
        warnings: List[ParseWarning] = []

        start_idx0 = tilt_end_idx0 or 0
        found = _find_photometry_header_line(lines, start_idx0=start_idx0)
        if found is not None:
            photometry_idx0, toks = found
            photometry = _parse_photometry_header_from_tokens(toks, line_no=photometry_idx0 + 1)
            angles, next_idx0 = _parse_angles_after_photometry(lines, photometry_idx0, photometry)
            candela = _parse_candela_table(lines, next_idx0, photometry, angles)
            angles, candela, norm_warnings = _normalize_angles_and_candela(angles, candela)
            warnings.extend(norm_warnings)
            if candela.max_cd >= 1_000_000.0:
                warnings.append(ParseWarning(code="extreme_candela_values", message="Candela values are unusually high.", line_no=None))

        if tilt_mode == "FILE" and tilt_data is None:
            warnings.append(ParseWarning(code="tilt_file_unresolved", message="Referenced TILT file could not be loaded.", line_no=None))

        for req in ("MANUFAC", "LUMCAT"):
            if req not in keywords or not keywords.get(req):
                warnings.append(ParseWarning(code="missing_keyword", message=f"Missing keyword: [{req}]", line_no=None))

        metadata = IESMetadata()
        if photometry is not None:
            dim_scale = 1.0 if int(photometry.units_type) == 2 else 0.3048
            dim_unit = "m" if int(photometry.units_type) == 2 else "ft"
            coord = {1: "Type C (C-gamma)", 2: "Type B (B-beta)", 3: "Type A (A-alpha)"}.get(int(photometry.photometric_type))
            cct: Optional[float] = None
            cri: Optional[float] = None
            dist: Optional[str] = None
            if keywords.get("CCT"):
                m = re.search(r"[+-]?\d+(\.\d+)?", str(keywords["CCT"][0]))
                if m:
                    cct = float(m.group(0))
            if keywords.get("CRI"):
                m = re.search(r"[+-]?\d+(\.\d+)?", str(keywords["CRI"][0]))
                if m:
                    cri = float(m.group(0))
            if keywords.get("DISTRIBUTION"):
                dist = str(keywords["DISTRIBUTION"][0]).strip() or None
            elif keywords.get("LUMCAT"):
                dist = str(keywords["LUMCAT"][0]).strip() or None

            metadata = IESMetadata(
                luminous_width_m=float(photometry.width) * dim_scale,
                luminous_length_m=float(photometry.length) * dim_scale,
                luminous_height_m=float(photometry.height) * dim_scale,
                luminous_dimensions_source_unit=dim_unit,
                lumens=float(photometry.num_lamps) * float(photometry.lumens_per_lamp),
                cct_k=cct,
                cri=cri,
                distribution_type=dist,
                coordinate_system=coord,
            )

        doc = ParsedIES(
            standard_line=standard_line,
            keywords=keywords,
            tilt_line=tilt_line,
            tilt_mode=tilt_mode,
            tilt_file_path=tilt_file_path,
            tilt_lamp_to_luminaire_geometry=tilt_lamp_to_luminaire_geometry,
            tilt_data=tilt_data,
            photometry=photometry,
            angles=angles,
            candela=candela,
            metadata=metadata,
            raw_lines=lines,
            warnings=warnings,
        )
        return doc
    except ParseError as e:
        if e.filename is None and src is not None:
            e.filename = str(src)
        raise


def parse_ies_file(path: str | Path) -> ParsedIES:
    p = Path(path).expanduser().resolve()
    try:
        text = p.read_text(encoding="utf-8")
        return parse_ies_text(text, source_path=p)
    except UnicodeDecodeError:
        text = p.read_text(encoding="cp1252", errors="replace")
        doc = parse_ies_text(text, source_path=p)
        doc.warnings.append(ParseWarning(code="encoding_fallback", message="Decoded using cp1252 fallback.", line_no=None))
        return doc


def _normalize_angles_and_candela(angles: AngleGrid, candela: CandelaGrid) -> tuple[AngleGrid, CandelaGrid, List[ParseWarning]]:
    warnings: List[ParseWarning] = []

    # Vertical angles: sort and deduplicate while averaging duplicate columns.
    v_raw = [float(x) for x in angles.vertical_deg]
    v_sorted = sorted(v_raw)
    if any(abs(a - b) > 1e-9 for a, b in zip(v_raw, v_sorted)):
        warnings.append(ParseWarning(code="vertical_angles_reordered", message="Vertical angles were reordered to ascending."))
    uniq_v: List[float] = []
    v_groups: List[List[int]] = []
    for idx, val in enumerate(v_raw):
        placed = False
        for gidx, u in enumerate(uniq_v):
            if abs(val - u) <= 1e-9:
                v_groups[gidx].append(idx)
                placed = True
                break
        if not placed:
            uniq_v.append(val)
            v_groups.append([idx])
    if len(uniq_v) < len(v_raw):
        warnings.append(ParseWarning(code="vertical_angles_deduplicated", message="Duplicate vertical angles were merged."))
    v_order = sorted(range(len(uniq_v)), key=lambda i: uniq_v[i])
    v_out = [uniq_v[i] for i in v_order]
    v_groups = [v_groups[i] for i in v_order]

    # Horizontal angles: normalize to [0,360), sort and deduplicate while averaging duplicate rows.
    h_raw = [float(x) for x in angles.horizontal_deg]
    h_mod = [((x % 360.0) + 360.0) % 360.0 for x in h_raw]
    if not any(abs(x) <= 1e-6 for x in h_mod):
        raise ParseError("Horizontal angle series must start at 0 degrees; Horizontal angle series must include 0 degrees")
    if any(abs(a - b) > 1e-9 for a, b in zip(h_raw, h_mod)):
        warnings.append(ParseWarning(code="horizontal_angles_reordered", message="Horizontal angles were normalized to [0,360)."))
    uniq_h: List[float] = []
    h_groups: List[List[int]] = []
    for idx, val in enumerate(h_mod):
        placed = False
        for gidx, u in enumerate(uniq_h):
            if abs(val - u) <= 1e-9:
                h_groups[gidx].append(idx)
                placed = True
                break
        if not placed:
            uniq_h.append(val)
            h_groups.append([idx])
    if len(uniq_h) < len(h_mod):
        warnings.append(ParseWarning(code="horizontal_angles_deduplicated", message="Duplicate horizontal angles were merged."))
    h_order = sorted(range(len(uniq_h)), key=lambda i: uniq_h[i])
    h_out = [uniq_h[i] for i in h_order]
    h_groups = [h_groups[i] for i in h_order]
    if any(abs(a - b) > 1e-9 for a, b in zip(h_mod, sorted(h_mod))):
        warnings.append(ParseWarning(code="horizontal_angles_reordered", message="Horizontal angles were reordered to ascending."))

    in_vals = candela.values_cd_scaled
    out_vals_scaled: List[List[float]] = []
    out_vals: List[List[float]] = []
    for h_idxes in h_groups:
        row: List[float] = []
        row_unscaled: List[float] = []
        for v_idxes in v_groups:
            samples_scaled: List[float] = []
            samples_raw: List[float] = []
            for hi in h_idxes:
                for vi in v_idxes:
                    samples_scaled.append(float(in_vals[hi][vi]))
                    samples_raw.append(float(candela.values_cd[hi][vi]))
            row.append(sum(samples_scaled) / max(1, len(samples_scaled)))
            row_unscaled.append(sum(samples_raw) / max(1, len(samples_raw)))
        out_vals_scaled.append(row)
        out_vals.append(row_unscaled)

    all_vals = [x for row in out_vals_scaled for x in row]
    out_candela = CandelaGrid(
        values_cd=out_vals,
        values_cd_scaled=out_vals_scaled,
        line_span=candela.line_span,
        min_cd=min(all_vals) if all_vals else 0.0,
        max_cd=max(all_vals) if all_vals else 0.0,
        has_negative=any(x < 0 for x in all_vals),
        has_nan_or_inf=any((math.isnan(x) or math.isinf(x)) for x in all_vals),
    )
    out_angles = AngleGrid(
        vertical_deg=v_out,
        horizontal_deg=h_out,
        vertical_line_span=angles.vertical_line_span,
        horizontal_line_span=angles.horizontal_line_span,
    )
    return out_angles, out_candela, warnings
