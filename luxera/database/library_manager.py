from __future__ import annotations

import json
import re
import shlex
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from luxera.core.hashing import sha256_file
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import LDTParseError, parse_ldt_text


SUPPORTED_EXTS = {".ies", ".ldt"}


@dataclass(frozen=True)
class LibraryEntry:
    id: int
    file_path: str
    file_name: str
    file_ext: str
    file_hash: str
    manufacturer: str
    name: str
    catalog_number: str
    lumens: Optional[float]
    cct: Optional[float]
    cri: Optional[float]
    beam_angle: Optional[float]
    distribution_type: str
    coordinate_system: str
    metadata_json: str
    parse_error: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": int(self.id),
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_ext": self.file_ext,
            "file_hash": self.file_hash,
            "manufacturer": self.manufacturer,
            "name": self.name,
            "catalog_number": self.catalog_number,
            "lumens": self.lumens,
            "cct": self.cct,
            "cri": self.cri,
            "beam_angle": self.beam_angle,
            "distribution_type": self.distribution_type,
            "coordinate_system": self.coordinate_system,
            "metadata": json.loads(self.metadata_json or "{}"),
            "parse_error": self.parse_error or None,
        }


@dataclass(frozen=True)
class IndexStats:
    scanned_files: int
    indexed_files: int
    parse_errors: int
    db_path: str


_NUM_RE = re.compile(r"^([a-z_]+)\s*(<=|>=|=|<|>)\s*([-+]?\d+(\.\d+)?)$", re.IGNORECASE)


def _round_float(value: Optional[float], digits: int = 6) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def _extract_keyword_numeric(keywords: Dict[str, List[str]], names: Sequence[str]) -> Optional[float]:
    num_re = re.compile(r"[-+]?\d+(\.\d+)?")
    upper = {str(k).strip().upper(): list(v) for k, v in keywords.items()}
    for name in names:
        values = upper.get(name.upper())
        if not values:
            continue
        for raw in values:
            m = num_re.search(str(raw))
            if not m:
                continue
            try:
                return float(m.group(0))
            except ValueError:
                continue
    return None


def _first_keyword(keywords: Dict[str, List[str]], names: Sequence[str]) -> str:
    upper = {str(k).strip().upper(): list(v) for k, v in keywords.items()}
    for name in names:
        values = upper.get(name.upper())
        if values:
            return str(values[0]).strip()
    return ""


def _estimate_beam_angle_from_ies(vertical_deg: Sequence[float], candela_rows: Sequence[Sequence[float]]) -> Optional[float]:
    if not vertical_deg or not candela_rows:
        return None
    row = candela_rows[0]
    if not row:
        return None
    peak = max(float(v) for v in row)
    if peak <= 0.0:
        return None
    threshold = 0.5 * peak
    center_idx = min(range(len(vertical_deg)), key=lambda i: abs(float(vertical_deg[i])))
    left = center_idx
    while left > 0 and float(row[left]) >= threshold:
        left -= 1
    right = center_idx
    while right < len(vertical_deg) - 1 and float(row[right]) >= threshold:
        right += 1
    return max(0.0, float(vertical_deg[right]) - float(vertical_deg[left]))


def _estimate_beam_angle_from_ldt(gamma_deg: Sequence[float], candela_rows: Sequence[Sequence[float]]) -> Optional[float]:
    if not gamma_deg or not candela_rows:
        return None
    row = candela_rows[0]
    if not row:
        return None
    peak = max(float(v) for v in row)
    if peak <= 0.0:
        return None
    threshold = 0.5 * peak
    idx_peak = max(range(len(row)), key=lambda i: float(row[i]))
    left = idx_peak
    while left > 0 and float(row[left]) >= threshold:
        left -= 1
    right = idx_peak
    while right < len(row) - 1 and float(row[right]) >= threshold:
        right += 1
    return max(0.0, float(gamma_deg[right]) - float(gamma_deg[left]))


def _parse_ies_file(path: Path, text: str) -> Dict[str, Any]:
    parsed = parse_ies_text(text, source_path=path)
    keywords = parsed.keywords
    manufacturer = _first_keyword(keywords, ["MANUFAC", "MANUFACTURER", "MFR"])
    name = _first_keyword(keywords, ["LUMINAIRE", "LUMINAIRENAME", "TEST"])
    catalog = _first_keyword(keywords, ["LUMCAT", "CATALOG", "CATALOG_NUMBER"])
    beam = _extract_keyword_numeric(keywords, ["BEAM", "BEAM_ANGLE", "BEAMANGLE"])
    if beam is None and parsed.angles is not None and parsed.candela is not None:
        beam = _estimate_beam_angle_from_ies(parsed.angles.vertical_deg, parsed.candela.values_cd_scaled)
    lumens = parsed.metadata.lumens
    cct = parsed.metadata.cct_k
    cri = parsed.metadata.cri
    distribution = parsed.metadata.distribution_type or ""
    coordinate_system = parsed.metadata.coordinate_system or ""
    metadata = parsed.metadata.to_dict()
    metadata["warnings"] = [w.to_dict() for w in parsed.warnings]
    return {
        "manufacturer": manufacturer or "Unknown",
        "name": name,
        "catalog_number": catalog,
        "lumens": _round_float(lumens),
        "cct": _round_float(cct),
        "cri": _round_float(cri),
        "beam_angle": _round_float(beam),
        "distribution_type": distribution,
        "coordinate_system": coordinate_system,
        "metadata": metadata,
        "parse_error": "",
    }


def _parse_ldt_file(text: str) -> Dict[str, Any]:
    parsed = parse_ldt_text(text)
    header = parsed.header
    total_lumens = sum(float(ls.total_flux) for ls in header.lamp_sets)
    cct = None
    cri = None
    for ls in header.lamp_sets:
        if cct is None:
            m = re.search(r"[-+]?\d+(\.\d+)?", str(ls.color_temperature))
            if m:
                cct = float(m.group(0))
        if cri is None:
            m = re.search(r"[-+]?\d+(\.\d+)?", str(ls.color_rendering))
            if m:
                cri = float(m.group(0))
    beam = _estimate_beam_angle_from_ldt(parsed.angles.g_angles_deg, parsed.candela.values_cd_scaled)
    distribution = f"type_{header.type_indicator}"
    coord = "Type C (C-gamma)"
    metadata = {
        "dff_percent": header.dff_percent,
        "lorl_percent": header.lorl_percent,
        "symmetry": header.symmetry,
        "num_c_planes": header.num_c_planes,
        "num_g_angles": header.num_g_angles,
    }
    return {
        "manufacturer": header.company or "Unknown",
        "name": header.luminaire_name,
        "catalog_number": header.luminaire_number,
        "lumens": _round_float(total_lumens if total_lumens > 0 else None),
        "cct": _round_float(cct),
        "cri": _round_float(cri),
        "beam_angle": _round_float(beam),
        "distribution_type": distribution,
        "coordinate_system": coord,
        "metadata": metadata,
        "parse_error": "",
    }


def _scan_photometry_files(folder: Path) -> List[Path]:
    files = []
    for p in sorted(folder.rglob("*"), key=lambda x: str(x).lower()):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            files.append(p.resolve())
    return files


def _open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS photometry_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            file_name TEXT NOT NULL,
            file_ext TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            manufacturer TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            catalog_number TEXT NOT NULL DEFAULT '',
            lumens REAL,
            cct REAL,
            cri REAL,
            beam_angle REAL,
            distribution_type TEXT NOT NULL DEFAULT '',
            coordinate_system TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            parse_error TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_manufacturer ON photometry_library(manufacturer)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_lumens ON photometry_library(lumens)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_cct ON photometry_library(cct)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_beam ON photometry_library(beam_angle)")
    conn.commit()
    return conn


def index_folder(folder: Path, db_path: Path) -> IndexStats:
    folder = folder.expanduser().resolve()
    db_path = db_path.expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder does not exist: {folder}")

    files = _scan_photometry_files(folder)
    conn = _open_db(db_path)
    indexed = 0
    parse_errors = 0
    try:
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            parsed: Dict[str, Any]
            parse_error = ""
            try:
                if path.suffix.lower() == ".ies":
                    parsed = _parse_ies_file(path, text)
                else:
                    parsed = _parse_ldt_file(text)
            except Exception as exc:
                parsed = {
                    "manufacturer": "Unknown",
                    "name": path.stem,
                    "catalog_number": "",
                    "lumens": None,
                    "cct": None,
                    "cri": None,
                    "beam_angle": None,
                    "distribution_type": "",
                    "coordinate_system": "",
                    "metadata": {},
                    "parse_error": str(exc),
                }
                parse_error = str(exc)
                parse_errors += 1

            file_hash = sha256_file(str(path))
            metadata_json = json.dumps(parsed.get("metadata", {}), sort_keys=True, separators=(",", ":"))
            conn.execute(
                """
                INSERT INTO photometry_library (
                    file_path, file_name, file_ext, file_hash,
                    manufacturer, name, catalog_number, lumens, cct, cri, beam_angle,
                    distribution_type, coordinate_system, metadata_json, parse_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_name=excluded.file_name,
                    file_ext=excluded.file_ext,
                    file_hash=excluded.file_hash,
                    manufacturer=excluded.manufacturer,
                    name=excluded.name,
                    catalog_number=excluded.catalog_number,
                    lumens=excluded.lumens,
                    cct=excluded.cct,
                    cri=excluded.cri,
                    beam_angle=excluded.beam_angle,
                    distribution_type=excluded.distribution_type,
                    coordinate_system=excluded.coordinate_system,
                    metadata_json=excluded.metadata_json,
                    parse_error=excluded.parse_error
                """,
                (
                    str(path),
                    path.name,
                    path.suffix.lower().lstrip("."),
                    file_hash,
                    str(parsed.get("manufacturer") or "Unknown"),
                    str(parsed.get("name") or ""),
                    str(parsed.get("catalog_number") or ""),
                    parsed.get("lumens"),
                    parsed.get("cct"),
                    parsed.get("cri"),
                    parsed.get("beam_angle"),
                    str(parsed.get("distribution_type") or ""),
                    str(parsed.get("coordinate_system") or ""),
                    metadata_json,
                    str(parsed.get("parse_error") or parse_error or ""),
                ),
            )
            indexed += 1
        conn.commit()
    finally:
        conn.close()

    return IndexStats(
        scanned_files=len(files),
        indexed_files=indexed,
        parse_errors=parse_errors,
        db_path=str(db_path),
    )


def _parse_query(query: str) -> tuple[List[tuple[str, str, float]], List[str], List[str]]:
    numeric_filters: List[tuple[str, str, float]] = []
    manufacturer_filters: List[str] = []
    keywords: List[str] = []
    tokens = shlex.split(query or "")
    for raw in tokens:
        tok = raw.strip()
        if not tok:
            continue
        low = tok.lower()
        if low.startswith("manufacturer:") or low.startswith("mfg:"):
            manufacturer_filters.append(tok.split(":", 1)[1].strip())
            continue
        m = _NUM_RE.match(tok)
        if m:
            field = str(m.group(1)).lower()
            op = str(m.group(2))
            value = float(m.group(3))
            if field in {"lumens", "cct", "beam", "beam_angle"}:
                numeric_filters.append((field, op, value))
                continue
        keywords.append(tok)
    return numeric_filters, manufacturer_filters, keywords


def _op_sql(op: str) -> str:
    if op not in {"<", "<=", "=", ">=", ">"}:
        raise ValueError(f"Unsupported operator: {op}")
    return op


def search_db(db_path: Path, query: str, *, limit: int = 100) -> List[LibraryEntry]:
    db_path = db_path.expanduser().resolve()
    conn = _open_db(db_path)
    numeric_filters, manufacturer_filters, keywords = _parse_query(query)

    clauses = ["1=1"]
    params: List[Any] = []
    for field, op, value in numeric_filters:
        col = "beam_angle" if field in {"beam", "beam_angle"} else field
        clauses.append(f"{col} {_op_sql(op)} ?")
        params.append(float(value))
    for mf in manufacturer_filters:
        clauses.append("LOWER(manufacturer) LIKE ?")
        params.append(f"%{mf.lower()}%")
    for kw in keywords:
        clauses.append(
            "(LOWER(manufacturer) LIKE ? OR LOWER(name) LIKE ? OR LOWER(catalog_number) LIKE ? OR LOWER(file_name) LIKE ? OR LOWER(file_path) LIKE ?)"
        )
        like = f"%{kw.lower()}%"
        params.extend([like, like, like, like, like])

    params.append(int(limit))
    rows = conn.execute(
        f"""
        SELECT *
        FROM photometry_library
        WHERE {' AND '.join(clauses)}
        ORDER BY LOWER(manufacturer), LOWER(name), LOWER(file_name), LOWER(file_path)
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    return [LibraryEntry(**dict(r)) for r in rows]


def list_all_entries(db_path: Path) -> List[LibraryEntry]:
    db_path = db_path.expanduser().resolve()
    conn = _open_db(db_path)
    rows = conn.execute(
        """
        SELECT *
        FROM photometry_library
        ORDER BY LOWER(manufacturer), LOWER(name), LOWER(file_name), LOWER(file_path)
        """
    ).fetchall()
    conn.close()
    return [LibraryEntry(**dict(r)) for r in rows]

