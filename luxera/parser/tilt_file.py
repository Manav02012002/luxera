from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from luxera.models.tilt import TiltData


class TiltFileError(ValueError):
    pass


@dataclass(frozen=True)
class TiltFilePayload:
    geometry_factor: str
    data: TiltData


def _tokenize_numeric_lines(lines: List[str], start_idx: int, count: int) -> Tuple[List[float], int]:
    values: List[float] = []
    idx = start_idx
    while idx < len(lines) and len(values) < count:
        s = lines[idx].strip()
        if s:
            for tok in s.split():
                if len(values) >= count:
                    break
                try:
                    values.append(float(tok))
                except ValueError as e:
                    raise TiltFileError(f"Invalid numeric token '{tok}' in tilt file line {idx + 1}") from e
        idx += 1
    if len(values) != count:
        raise TiltFileError(f"Tilt file numeric block expected {count} values, found {len(values)}")
    return values, idx


def load_tilt_file_payload(path: Path) -> TiltFilePayload:
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise TiltFileError(f"Tilt file not found: {p}")
    lines = [ln.rstrip("\r\n") for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()]
    if not lines:
        raise TiltFileError(f"Tilt file is empty: {p}")

    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        raise TiltFileError(f"Tilt file has no payload: {p}")

    geometry_factor = lines[idx].strip()
    idx += 1

    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        raise TiltFileError("Tilt file missing angle count")

    try:
        n = int(float(lines[idx].strip().split()[0]))
    except Exception as e:
        raise TiltFileError(f"Tilt file angle count is invalid on line {idx + 1}") from e
    idx += 1
    if n <= 0:
        raise TiltFileError("Tilt file angle count must be > 0")

    angles, idx = _tokenize_numeric_lines(lines, idx, n)
    factors, _ = _tokenize_numeric_lines(lines, idx, n)
    data = TiltData(angles_deg=[float(x) for x in angles], factors=[float(x) for x in factors])
    try:
        data.validate()
    except ValueError as e:
        raise TiltFileError(str(e)) from e
    return TiltFilePayload(geometry_factor=geometry_factor, data=data)


def load_tilt_file(path: Path) -> TiltData:
    return load_tilt_file_payload(path).data
