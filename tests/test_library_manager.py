from __future__ import annotations

import json
from pathlib import Path

from luxera.database.library_manager import index_folder, list_all_entries, search_db


def _ies_text(*, manufacturer: str, name: str, catalog: str, lumens: float, cct: int, beam: float) -> str:
    return f"""IESNA:LM-63-2002
[MANUFAC] {manufacturer}
[LUMINAIRE] {name}
[LUMCAT] {catalog}
[CCT] {cct}
[BEAM] {beam}
TILT=NONE
1 {lumens} 1 3 2 1 2 0.50 0.50 0.10
0 30 90
0 180
100 80 20
100 80 20
"""


def _norm_entries(db_path: Path) -> list[dict]:
    rows = [r.to_dict() for r in list_all_entries(db_path)]
    out = []
    for r in rows:
        item = dict(r)
        item.pop("id", None)
        out.append(item)
    return out


def test_library_indexing_is_deterministic(tmp_path: Path) -> None:
    folder = tmp_path / "lib"
    folder.mkdir()
    (folder / "b_wide.ies").write_text(
        _ies_text(
            manufacturer="Beta Lighting",
            name="Wide Bay",
            catalog="B-200",
            lumens=2400.0,
            cct=4000,
            beam=90.0,
        ),
        encoding="utf-8",
    )
    (folder / "a_narrow.ies").write_text(
        _ies_text(
            manufacturer="Acme Lighting",
            name="Narrow Spot",
            catalog="A-100",
            lumens=1200.0,
            cct=3000,
            beam=30.0,
        ),
        encoding="utf-8",
    )
    ldt_fixture = Path("tests/fixtures/photometry/synthetic_basic.ldt").read_text(encoding="utf-8")
    (folder / "c_fixture.ldt").write_text(ldt_fixture, encoding="utf-8")

    db1 = tmp_path / "lib1.db"
    db2 = tmp_path / "lib2.db"
    stats1 = index_folder(folder, db1)
    stats2 = index_folder(folder, db2)
    assert stats1.scanned_files == 3
    assert stats2.scanned_files == 3
    assert _norm_entries(db1) == _norm_entries(db2)


def test_library_search_filters(tmp_path: Path) -> None:
    folder = tmp_path / "lib"
    folder.mkdir()
    (folder / "narrow.ies").write_text(
        _ies_text(
            manufacturer="Acme Lighting",
            name="Narrow Spot",
            catalog="A-100",
            lumens=1200.0,
            cct=3000,
            beam=30.0,
        ),
        encoding="utf-8",
    )
    (folder / "wide.ies").write_text(
        _ies_text(
            manufacturer="RoadPro",
            name="Wide Flood",
            catalog="R-250",
            lumens=4200.0,
            cct=5000,
            beam=110.0,
        ),
        encoding="utf-8",
    )
    db = tmp_path / "library.db"
    index_folder(folder, db)

    q1 = search_db(db, "manufacturer:acme")
    assert [r.catalog_number for r in q1] == ["A-100"]

    q2 = search_db(db, "lumens>=2000")
    assert [r.catalog_number for r in q2] == ["R-250"]

    q3 = search_db(db, "cct=3000")
    assert [r.catalog_number for r in q3] == ["A-100"]

    q4 = search_db(db, "beam<50")
    assert [r.catalog_number for r in q4] == ["A-100"]

    q5 = search_db(db, "wide")
    assert [r.catalog_number for r in q5] == ["R-250"]


def test_library_index_and_search_json_shape(tmp_path: Path) -> None:
    folder = tmp_path / "lib"
    folder.mkdir()
    (folder / "one.ies").write_text(
        _ies_text(
            manufacturer="Acme",
            name="One",
            catalog="CAT-1",
            lumens=1000.0,
            cct=3500,
            beam=45.0,
        ),
        encoding="utf-8",
    )
    db = tmp_path / "db.sqlite"
    index_folder(folder, db)
    rows = [r.to_dict() for r in search_db(db, "manufacturer:acme")]
    assert len(rows) == 1
    assert rows[0]["file_ext"] == "ies"
    assert json.dumps(rows, sort_keys=True)

