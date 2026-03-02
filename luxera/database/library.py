from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt


@dataclass(frozen=True)
class PhotometryRecord:
    id: str
    file_path: str
    file_format: str
    manufacturer: Optional[str]
    catalog_number: Optional[str]
    luminaire_description: Optional[str]
    lamp_type: Optional[str]
    total_lumens: float
    beam_angle_deg: Optional[float]
    field_angle_deg: Optional[float]
    max_intensity_cd: float
    cri: Optional[float]
    cct_k: Optional[float]
    wattage: Optional[float]
    efficacy_lm_per_w: Optional[float]
    photometric_type: str
    symmetry: str
    luminous_width_mm: Optional[float]
    luminous_length_mm: Optional[float]
    ies_version: Optional[str]
    keywords: Dict[str, str]
    indexed_at: str


def _first_float(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", str(s))
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _kw_get(keywords: Dict[str, List[str]], *names: str) -> Optional[str]:
    upper = {str(k).upper(): v for k, v in keywords.items()}
    for name in names:
        vals = upper.get(name.upper())
        if isinstance(vals, list) and vals:
            return str(vals[0]).strip()
    return None


def _compute_beam_and_field_angles(angles_deg: np.ndarray, candela_row: np.ndarray) -> tuple[Optional[float], Optional[float], float]:
    if angles_deg.size == 0 or candela_row.size == 0 or angles_deg.size != candela_row.size:
        return None, None, 0.0
    peak = float(np.max(candela_row))
    if peak <= 1e-12:
        return None, None, 0.0
    beam_target = 0.5 * peak
    field_target = 0.1 * peak

    def _crossing(target: float) -> Optional[float]:
        for i in range(1, len(candela_row)):
            c0 = float(candela_row[i - 1])
            c1 = float(candela_row[i])
            if c0 >= target >= c1:
                a0 = float(angles_deg[i - 1])
                a1 = float(angles_deg[i])
                if abs(c1 - c0) < 1e-12:
                    return a1
                t = (target - c0) / (c1 - c0)
                return a0 + (a1 - a0) * t
        return None

    return _crossing(beam_target), _crossing(field_target), peak


class PhotometryLibrary:
    """
    SQLite-backed photometric file library with search and filtering.
    """

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path).expanduser().resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS photometry_library (
                id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                file_format TEXT NOT NULL,
                manufacturer TEXT,
                catalog_number TEXT,
                luminaire_description TEXT,
                lamp_type TEXT,
                total_lumens REAL NOT NULL,
                beam_angle_deg REAL,
                field_angle_deg REAL,
                max_intensity_cd REAL NOT NULL,
                cri REAL,
                cct_k REAL,
                wattage REAL,
                efficacy_lm_per_w REAL,
                photometric_type TEXT NOT NULL,
                symmetry TEXT NOT NULL,
                luminous_width_mm REAL,
                luminous_length_mm REAL,
                ies_version TEXT,
                keywords_json TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_plib_manufacturer ON photometry_library(manufacturer)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_plib_lumens ON photometry_library(total_lumens)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_plib_beam ON photometry_library(beam_angle_deg)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_plib_format ON photometry_library(file_format)")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "PhotometryLibrary":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _row_to_record(self, row: sqlite3.Row) -> PhotometryRecord:
        kw = row["keywords_json"]
        keywords = json.loads(kw) if isinstance(kw, str) and kw else {}
        if not isinstance(keywords, dict):
            keywords = {}
        return PhotometryRecord(
            id=str(row["id"]),
            file_path=str(row["file_path"]),
            file_format=str(row["file_format"]),
            manufacturer=row["manufacturer"],
            catalog_number=row["catalog_number"],
            luminaire_description=row["luminaire_description"],
            lamp_type=row["lamp_type"],
            total_lumens=float(row["total_lumens"] or 0.0),
            beam_angle_deg=(None if row["beam_angle_deg"] is None else float(row["beam_angle_deg"])),
            field_angle_deg=(None if row["field_angle_deg"] is None else float(row["field_angle_deg"])),
            max_intensity_cd=float(row["max_intensity_cd"] or 0.0),
            cri=(None if row["cri"] is None else float(row["cri"])),
            cct_k=(None if row["cct_k"] is None else float(row["cct_k"])),
            wattage=(None if row["wattage"] is None else float(row["wattage"])),
            efficacy_lm_per_w=(None if row["efficacy_lm_per_w"] is None else float(row["efficacy_lm_per_w"])),
            photometric_type=str(row["photometric_type"]),
            symmetry=str(row["symmetry"]),
            luminous_width_mm=(None if row["luminous_width_mm"] is None else float(row["luminous_width_mm"])),
            luminous_length_mm=(None if row["luminous_length_mm"] is None else float(row["luminous_length_mm"])),
            ies_version=row["ies_version"],
            keywords={str(k): str(v) for k, v in keywords.items()},
            indexed_at=str(row["indexed_at"]),
        )

    def _insert_record(self, rec: PhotometryRecord) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO photometry_library (
                id, file_path, file_format, manufacturer, catalog_number, luminaire_description, lamp_type,
                total_lumens, beam_angle_deg, field_angle_deg, max_intensity_cd, cri, cct_k, wattage,
                efficacy_lm_per_w, photometric_type, symmetry, luminous_width_mm, luminous_length_mm,
                ies_version, keywords_json, indexed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec.id,
                rec.file_path,
                rec.file_format,
                rec.manufacturer,
                rec.catalog_number,
                rec.luminaire_description,
                rec.lamp_type,
                rec.total_lumens,
                rec.beam_angle_deg,
                rec.field_angle_deg,
                rec.max_intensity_cd,
                rec.cri,
                rec.cct_k,
                rec.wattage,
                rec.efficacy_lm_per_w,
                rec.photometric_type,
                rec.symmetry,
                rec.luminous_width_mm,
                rec.luminous_length_mm,
                rec.ies_version,
                json.dumps(rec.keywords, sort_keys=True),
                rec.indexed_at,
            ),
        )

    def _build_record_ies(self, path: Path, text: str, digest: str) -> PhotometryRecord:
        doc = parse_ies_text(text, source_path=path)
        phot = photometry_from_parsed_ies(doc)
        c0 = np.asarray(phot.candela[0], dtype=float) if np.asarray(phot.candela).ndim == 2 else np.array([], dtype=float)
        beam, field, max_cd = _compute_beam_and_field_angles(np.asarray(phot.gamma_angles_deg, dtype=float), c0)

        manufacturer = _kw_get(doc.keywords, "MANUFAC", "MANUFACTURER")
        catalog = _kw_get(doc.keywords, "LUMCAT", "CATALOG", "CAT")
        desc = _kw_get(doc.keywords, "LUMINAIRE", "TEST", "DESCRIPTION")
        lamp_type = _kw_get(doc.keywords, "LAMPCAT", "LAMP", "LAMP_TYPE")
        cri = _first_float(_kw_get(doc.keywords, "CRI", "RA", "COLORRENDERING"))
        cct = _first_float(_kw_get(doc.keywords, "CCT", "CCTK", "COLOURTEMPERATURE"))
        watts = _first_float(_kw_get(doc.keywords, "WATTS", "INPUTWATTS", "LUMINAIREWATTS"))
        lumens = float(phot.luminous_flux_lm or 0.0)
        efficacy = (lumens / watts) if (watts is not None and watts > 1e-9) else None

        keywords = {str(k): str(v[0] if isinstance(v, list) and v else v) for k, v in doc.keywords.items()}
        return PhotometryRecord(
            id=digest,
            file_path=str(path),
            file_format="IES",
            manufacturer=manufacturer,
            catalog_number=catalog,
            luminaire_description=desc,
            lamp_type=lamp_type,
            total_lumens=lumens,
            beam_angle_deg=beam,
            field_angle_deg=field,
            max_intensity_cd=max_cd,
            cri=cri,
            cct_k=cct,
            wattage=watts,
            efficacy_lm_per_w=efficacy,
            photometric_type=str(phot.system),
            symmetry=str(phot.symmetry),
            luminous_width_mm=(None if phot.luminous_width_m is None else float(phot.luminous_width_m) * 1000.0),
            luminous_length_mm=(None if phot.luminous_length_m is None else float(phot.luminous_length_m) * 1000.0),
            ies_version=(doc.standard_line or None),
            keywords=keywords,
            indexed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _build_record_ldt(self, path: Path, text: str, digest: str) -> PhotometryRecord:
        doc = parse_ldt_text(text)
        phot = photometry_from_parsed_ldt(doc)
        c0 = np.asarray(phot.candela[0], dtype=float) if np.asarray(phot.candela).ndim == 2 else np.array([], dtype=float)
        beam, field, max_cd = _compute_beam_and_field_angles(np.asarray(phot.gamma_angles_deg, dtype=float), c0)

        lumens = float(doc.header.lamp_sets[0].total_flux) if doc.header.lamp_sets else float(phot.luminous_flux_lm or 0.0)
        watts = float(doc.header.lamp_sets[0].wattage) if doc.header.lamp_sets else None
        efficacy = (lumens / watts) if (watts is not None and watts > 1e-9) else None
        cri = _first_float(doc.header.lamp_sets[0].color_rendering) if doc.header.lamp_sets else None
        cct = _first_float(doc.header.lamp_sets[0].color_temperature) if doc.header.lamp_sets else None

        keywords = {
            "company": doc.header.company,
            "luminaire_name": doc.header.luminaire_name,
            "luminaire_number": doc.header.luminaire_number,
            "filename": doc.header.filename,
            "lamp_type": (doc.header.lamp_sets[0].lamp_type if doc.header.lamp_sets else ""),
        }

        return PhotometryRecord(
            id=digest,
            file_path=str(path),
            file_format="LDT",
            manufacturer=(doc.header.company or None),
            catalog_number=(doc.header.luminaire_number or None),
            luminaire_description=(doc.header.luminaire_name or None),
            lamp_type=(doc.header.lamp_sets[0].lamp_type if doc.header.lamp_sets else None),
            total_lumens=lumens,
            beam_angle_deg=beam,
            field_angle_deg=field,
            max_intensity_cd=max_cd,
            cri=cri,
            cct_k=cct,
            wattage=watts,
            efficacy_lm_per_w=efficacy,
            photometric_type=str(phot.system),
            symmetry=str(phot.symmetry),
            luminous_width_mm=(None if phot.luminous_width_m is None else float(phot.luminous_width_m) * 1000.0),
            luminous_length_mm=(None if phot.luminous_length_m is None else float(phot.luminous_length_m) * 1000.0),
            ies_version=None,
            keywords=keywords,
            indexed_at=datetime.now(timezone.utc).isoformat(),
        )

    def index_directory(self, directory: Path, recursive: bool = True) -> int:
        """
        Scan directory for .ies and .ldt files and index them. Return count indexed.
        """
        root = Path(directory).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Not a directory: {root}")
        pattern_iter = root.rglob("*") if recursive else root.glob("*")
        indexed = 0
        for p in pattern_iter:
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext not in {".ies", ".ldt"}:
                continue
            try:
                raw = p.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                exists = self._conn.execute("SELECT 1 FROM photometry_library WHERE id = ?", (digest,)).fetchone()
                if exists is not None:
                    continue
                text = raw.decode("utf-8", errors="replace")
                if ext == ".ies":
                    rec = self._build_record_ies(p, text, digest)
                else:
                    rec = self._build_record_ldt(p, text, digest)
                self._insert_record(rec)
                indexed += 1
            except Exception as e:
                print(f"[library:index] warning: failed to index {p}: {e}")
                continue
        self._conn.commit()
        return indexed

    def search(
        self,
        query: Optional[str] = None,
        manufacturer: Optional[str] = None,
        min_lumens: Optional[float] = None,
        max_lumens: Optional[float] = None,
        min_beam_angle: Optional[float] = None,
        max_beam_angle: Optional[float] = None,
        min_cct: Optional[float] = None,
        max_cct: Optional[float] = None,
        file_format: Optional[str] = None,
        photometric_type: Optional[str] = None,
        sort_by: str = "total_lumens",
        sort_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[PhotometryRecord], int]:
        where: List[str] = []
        params: List[Any] = []
        if query:
            q = f"%{query.strip()}%"
            where.append("(manufacturer LIKE ? OR catalog_number LIKE ? OR luminaire_description LIKE ?)")
            params.extend([q, q, q])
        if manufacturer:
            where.append("manufacturer LIKE ?")
            params.append(f"%{manufacturer.strip()}%")
        if min_lumens is not None:
            where.append("total_lumens >= ?")
            params.append(float(min_lumens))
        if max_lumens is not None:
            where.append("total_lumens <= ?")
            params.append(float(max_lumens))
        if min_beam_angle is not None:
            where.append("beam_angle_deg >= ?")
            params.append(float(min_beam_angle))
        if max_beam_angle is not None:
            where.append("beam_angle_deg <= ?")
            params.append(float(max_beam_angle))
        if min_cct is not None:
            where.append("cct_k >= ?")
            params.append(float(min_cct))
        if max_cct is not None:
            where.append("cct_k <= ?")
            params.append(float(max_cct))
        if file_format:
            where.append("file_format = ?")
            params.append(str(file_format).upper())
        if photometric_type:
            where.append("photometric_type = ?")
            params.append(str(photometric_type).upper())

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        sortable = {
            "id",
            "file_path",
            "file_format",
            "manufacturer",
            "catalog_number",
            "luminaire_description",
            "total_lumens",
            "beam_angle_deg",
            "field_angle_deg",
            "max_intensity_cd",
            "cri",
            "cct_k",
            "wattage",
            "efficacy_lm_per_w",
            "photometric_type",
            "symmetry",
            "indexed_at",
        }
        col = sort_by if sort_by in sortable else "total_lumens"
        direction = "DESC" if sort_desc else "ASC"
        total = self._conn.execute(f"SELECT COUNT(*) FROM photometry_library{where_sql}", params).fetchone()[0]
        rows = self._conn.execute(
            f"SELECT * FROM photometry_library{where_sql} ORDER BY {col} {direction} LIMIT ? OFFSET ?",
            [*params, int(limit), int(offset)],
        ).fetchall()
        return [self._row_to_record(r) for r in rows], int(total)

    def get_record(self, record_id: str) -> Optional[PhotometryRecord]:
        row = self._conn.execute("SELECT * FROM photometry_library WHERE id = ?", (record_id,)).fetchone()
        return None if row is None else self._row_to_record(row)

    def get_manufacturers(self) -> List[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT manufacturer FROM photometry_library WHERE manufacturer IS NOT NULL AND manufacturer <> '' ORDER BY manufacturer ASC"
        ).fetchall()
        return [str(r[0]) for r in rows]

    def get_statistics(self) -> Dict[str, Any]:
        total = int(self._conn.execute("SELECT COUNT(*) FROM photometry_library").fetchone()[0])
        mf_count = int(
            self._conn.execute(
                "SELECT COUNT(DISTINCT manufacturer) FROM photometry_library WHERE manufacturer IS NOT NULL AND manufacturer <> ''"
            ).fetchone()[0]
        )
        formats = {
            str(fmt): int(cnt)
            for fmt, cnt in self._conn.execute(
                "SELECT file_format, COUNT(*) FROM photometry_library GROUP BY file_format"
            ).fetchall()
        }
        return {"total_files": total, "manufacturers": mf_count, "format_breakdown": formats}

    def remove_missing_files(self) -> int:
        rows = self._conn.execute("SELECT id, file_path FROM photometry_library").fetchall()
        remove_ids: List[str] = []
        for r in rows:
            p = Path(str(r["file_path"])).expanduser()
            if not p.exists():
                remove_ids.append(str(r["id"]))
        if not remove_ids:
            return 0
        self._conn.executemany("DELETE FROM photometry_library WHERE id = ?", [(x,) for x in remove_ids])
        self._conn.commit()
        return len(remove_ids)

