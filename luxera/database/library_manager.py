from __future__ import annotations

import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Optional

from luxera.parser.ies_parser import parse_ies_file


@dataclass(frozen=True)
class LibraryEntry:
    id: int
    path: str
    file_ext: str
    manufacturer: str
    name: str
    catalog_number: str
    lumens: float
    cct: Optional[int]
    beam: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IndexStats:
    scanned_files: int
    indexed_files: int
    failed_files: int


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS library_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            file_ext TEXT NOT NULL,
            manufacturer TEXT NOT NULL,
            name TEXT NOT NULL,
            catalog_number TEXT NOT NULL,
            lumens REAL NOT NULL,
            cct INTEGER NULL,
            beam REAL NULL
        )
        """
    )
    return conn


def _parse_keyword_num(keywords: dict, key: str) -> Optional[float]:
    vals = keywords.get(key, [])
    if not vals:
        return None
    try:
        return float(str(vals[0]).strip())
    except Exception:
        return None


def _parse_ies_entry(path: Path) -> LibraryEntry:
    doc = parse_ies_file(path)
    keywords = doc.keywords or {}
    manufacturer = str((keywords.get("MANUFAC") or [""])[0] or "")
    name = str((keywords.get("LUMINAIRE") or [""])[0] or "")
    catalog = str((keywords.get("LUMCAT") or [path.stem])[0] or path.stem)
    lumens = 0.0
    if doc.photometry is not None:
        lumens = float(doc.photometry.num_lamps) * float(doc.photometry.lumens_per_lamp)
    cct_v = _parse_keyword_num(keywords, "CCT")
    beam_v = _parse_keyword_num(keywords, "BEAM")
    return LibraryEntry(
        id=0,
        path=str(path),
        file_ext="ies",
        manufacturer=manufacturer,
        name=name,
        catalog_number=catalog,
        lumens=lumens,
        cct=int(cct_v) if cct_v is not None else None,
        beam=float(beam_v) if beam_v is not None else None,
    )


def _parse_ldt_entry(path: Path) -> LibraryEntry:
    return LibraryEntry(
        id=0,
        path=str(path),
        file_ext="ldt",
        manufacturer="",
        name=path.stem,
        catalog_number=path.stem,
        lumens=0.0,
        cct=None,
        beam=None,
    )


def index_folder(folder: str | Path, db_path: str | Path) -> IndexStats:
    root = Path(folder).expanduser().resolve()
    db = Path(db_path).expanduser().resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db)
    scanned = 0
    indexed = 0
    failed = 0
    try:
        conn.execute("DELETE FROM library_entries")
        files = sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".ies", ".ldt"}], key=lambda p: str(p))
        for path in files:
            scanned += 1
            try:
                entry = _parse_ies_entry(path) if path.suffix.lower() == ".ies" else _parse_ldt_entry(path)
                conn.execute(
                    """
                    INSERT INTO library_entries(path,file_ext,manufacturer,name,catalog_number,lumens,cct,beam)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        entry.path,
                        entry.file_ext,
                        entry.manufacturer,
                        entry.name,
                        entry.catalog_number,
                        float(entry.lumens),
                        entry.cct,
                        entry.beam,
                    ),
                )
                indexed += 1
            except Exception:
                failed += 1
        conn.commit()
        return IndexStats(scanned_files=scanned, indexed_files=indexed, failed_files=failed)
    finally:
        conn.close()


def _rows_to_entries(rows: Iterable[sqlite3.Row]) -> List[LibraryEntry]:
    out: List[LibraryEntry] = []
    for r in rows:
        out.append(
            LibraryEntry(
                id=int(r["id"]),
                path=str(r["path"]),
                file_ext=str(r["file_ext"]),
                manufacturer=str(r["manufacturer"]),
                name=str(r["name"]),
                catalog_number=str(r["catalog_number"]),
                lumens=float(r["lumens"]),
                cct=(int(r["cct"]) if r["cct"] is not None else None),
                beam=(float(r["beam"]) if r["beam"] is not None else None),
            )
        )
    return out


def list_all_entries(db_path: str | Path) -> List[LibraryEntry]:
    conn = _connect(Path(db_path).expanduser().resolve())
    try:
        rows = conn.execute("SELECT * FROM library_entries ORDER BY id ASC").fetchall()
        return _rows_to_entries(rows)
    finally:
        conn.close()


def search_db(db_path: str | Path, query: str) -> List[LibraryEntry]:
    q = str(query or "").strip().lower()
    conn = _connect(Path(db_path).expanduser().resolve())
    try:
        if ":" in q:
            k, v = q.split(":", 1)
            if k == "manufacturer":
                rows = conn.execute(
                    "SELECT * FROM library_entries WHERE LOWER(manufacturer) LIKE ? ORDER BY id ASC",
                    (f"%{v.strip()}%",),
                ).fetchall()
                return _rows_to_entries(rows)
        for op in (">=", "<=", "=", ">", "<"):
            if op in q:
                k, rhs = q.split(op, 1)
                key = k.strip()
                try:
                    val = float(rhs.strip())
                except Exception:
                    break
                if key in {"lumens", "cct", "beam"}:
                    rows = conn.execute(
                        f"SELECT * FROM library_entries WHERE {key} {op} ? ORDER BY id ASC",
                        (val,),
                    ).fetchall()
                    return _rows_to_entries(rows)
        rows = conn.execute(
            """
            SELECT * FROM library_entries
            WHERE LOWER(name) LIKE ? OR LOWER(manufacturer) LIKE ? OR LOWER(catalog_number) LIKE ?
            ORDER BY id ASC
            """,
            (f"%{q}%", f"%{q}%", f"%{q}%"),
        ).fetchall()
        return _rows_to_entries(rows)
    finally:
        conn.close()
