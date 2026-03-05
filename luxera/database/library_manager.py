from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from luxera.database.library import PhotometryLibrary, PhotometryRecord


@dataclass(frozen=True)
class IndexStats:
    scanned_files: int
    indexed_files: int


@dataclass(frozen=True)
class LibraryEntry:
    id: str
    file_path: str
    file_ext: str
    manufacturer: Optional[str]
    catalog_number: Optional[str]
    luminaire_description: Optional[str]
    lamp_type: Optional[str]
    lumens: float
    beam_angle_deg: Optional[float]
    cct_k: Optional[float]

    def to_dict(self) -> dict:
        # Intentionally omit volatile timestamps to keep deterministic snapshots stable.
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_ext": self.file_ext,
            "manufacturer": self.manufacturer,
            "catalog_number": self.catalog_number,
            "luminaire_description": self.luminaire_description,
            "lamp_type": self.lamp_type,
            "lumens": self.lumens,
            "beam_angle_deg": self.beam_angle_deg,
            "cct_k": self.cct_k,
        }


def _to_entry(r: PhotometryRecord) -> LibraryEntry:
    beam_kw = None
    cct_kw = None
    if isinstance(r.keywords, dict):
        b = r.keywords.get("BEAM") or r.keywords.get("beam")
        c = r.keywords.get("CCT") or r.keywords.get("cct")
        try:
            beam_kw = float(b) if b is not None else None
        except Exception:
            beam_kw = None
        try:
            cct_kw = float(c) if c is not None else None
        except Exception:
            cct_kw = None
    return LibraryEntry(
        id=str(r.id),
        file_path=str(r.file_path),
        file_ext=str(r.file_format).lower(),
        manufacturer=r.manufacturer,
        catalog_number=r.catalog_number,
        luminaire_description=r.luminaire_description,
        lamp_type=r.lamp_type,
        lumens=float(r.total_lumens),
        beam_angle_deg=(beam_kw if beam_kw is not None else (None if r.beam_angle_deg is None else float(r.beam_angle_deg))),
        cct_k=(cct_kw if cct_kw is not None else (None if r.cct_k is None else float(r.cct_k))),
    )


def index_folder(folder: Path | str, db_path: Path | str) -> IndexStats:
    root = Path(folder).expanduser().resolve()
    scanned = 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".ies", ".ldt"}:
            scanned += 1

    with PhotometryLibrary(Path(db_path)) as lib:
        indexed = int(lib.index_directory(root, recursive=True))
    return IndexStats(scanned_files=scanned, indexed_files=indexed)


def list_all_entries(db_path: Path | str) -> List[LibraryEntry]:
    with PhotometryLibrary(Path(db_path)) as lib:
        rows, _ = lib.search(sort_by="file_path", sort_desc=False, limit=1_000_000, offset=0)
    return [_to_entry(r) for r in rows]


def search_db(db_path: Path | str, query: str) -> List[LibraryEntry]:
    q = (query or "").strip()
    if not q:
        return list_all_entries(db_path)

    kwargs = {}
    free_text = q

    # Small compatibility parser for historical query syntax.
    if ":" in q and q.split(":", 1)[0].strip().lower() == "manufacturer":
        kwargs["manufacturer"] = q.split(":", 1)[1].strip()
        free_text = ""
    elif q.lower().startswith("lumens>="):
        kwargs["min_lumens"] = float(q.split("=", 1)[1])
        free_text = ""
    elif q.lower().startswith("lumens<="):
        kwargs["max_lumens"] = float(q.split("=", 1)[1])
        free_text = ""
    elif q.lower().startswith("cct="):
        v = float(q.split("=", 1)[1])
        kwargs["min_cct"] = v
        kwargs["max_cct"] = v
        free_text = ""
    elif q.lower().startswith("beam<"):
        kwargs["max_beam_angle"] = float(q.split("<", 1)[1])
        free_text = ""
    elif q.lower().startswith("beam>"):
        kwargs["min_beam_angle"] = float(q.split(">", 1)[1])
        free_text = ""

    # Beam-angle comparator compatibility is evaluated against effective entry
    # values (keyword override + parsed value), so we filter in-memory.
    if q.lower().startswith("beam<") or q.lower().startswith("beam>"):
        threshold = float(q[5:].strip())
        all_rows = list_all_entries(db_path)
        if q.lower().startswith("beam<"):
            return [r for r in all_rows if r.beam_angle_deg is not None and float(r.beam_angle_deg) < threshold]
        return [r for r in all_rows if r.beam_angle_deg is not None and float(r.beam_angle_deg) > threshold]

    with PhotometryLibrary(Path(db_path)) as lib:
        rows, _ = lib.search(query=free_text or None, sort_by="file_path", sort_desc=False, limit=10_000, offset=0, **kwargs)
    return [_to_entry(r) for r in rows]
