from __future__ import annotations

from pathlib import Path

from luxera.database.library import PhotometryLibrary


def _ies_text(*, manufacturer: str, name: str, catalog: str, lumens: float, cct: int) -> str:
    return f"""IESNA:LM-63-2002
[MANUFAC] {manufacturer}
[LUMINAIRE] {name}
[LUMCAT] {catalog}
[CCT] {cct}
TILT=NONE
1 {lumens} 1 4 1 1 2 0.50 0.50 0.10
0 30 60 90
0
100 60 10 2
"""


def _make_fixture_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "ies_lib"
    folder.mkdir()
    (folder / "a_office.ies").write_text(
        _ies_text(
            manufacturer="Acme",
            name="Office Panel",
            catalog="AC-100",
            lumens=3200.0,
            cct=4000,
        ),
        encoding="utf-8",
    )
    (folder / "b_spot.ies").write_text(
        _ies_text(
            manufacturer="BetaLight",
            name="Retail Spot",
            catalog="BL-200",
            lumens=1800.0,
            cct=3000,
        ),
        encoding="utf-8",
    )
    (folder / "c_flood.ies").write_text(
        _ies_text(
            manufacturer="Acme",
            name="Outdoor Flood",
            catalog="AC-300",
            lumens=7200.0,
            cct=5000,
        ),
        encoding="utf-8",
    )
    return folder


def test_index_directory(tmp_path: Path):
    folder = _make_fixture_dir(tmp_path)
    db = tmp_path / "library.sqlite"
    with PhotometryLibrary(db) as lib:
        indexed = lib.index_directory(folder, recursive=True)
        stats = lib.get_statistics()
    assert indexed == 3
    assert stats["total_files"] == 3


def test_search_by_manufacturer(tmp_path: Path):
    folder = _make_fixture_dir(tmp_path)
    db = tmp_path / "library.sqlite"
    with PhotometryLibrary(db) as lib:
        lib.index_directory(folder, recursive=True)
        rows, total = lib.search(manufacturer="Acme")
    assert total == 2
    assert len(rows) == 2


def test_search_by_lumens_range(tmp_path: Path):
    folder = _make_fixture_dir(tmp_path)
    db = tmp_path / "library.sqlite"
    with PhotometryLibrary(db) as lib:
        lib.index_directory(folder, recursive=True)
        rows, total = lib.search(min_lumens=1000, max_lumens=5000)
    assert total == 2
    assert all(1000 <= r.total_lumens <= 5000 for r in rows)


def test_free_text_search(tmp_path: Path):
    folder = _make_fixture_dir(tmp_path)
    db = tmp_path / "library.sqlite"
    with PhotometryLibrary(db) as lib:
        lib.index_directory(folder, recursive=True)
        rows, total = lib.search(query="office")
    assert total == 1
    assert rows[0].catalog_number == "AC-100"


def test_beam_angle_computed(tmp_path: Path):
    folder = _make_fixture_dir(tmp_path)
    db = tmp_path / "library.sqlite"
    with PhotometryLibrary(db) as lib:
        lib.index_directory(folder, recursive=True)
        rows, total = lib.search(limit=1)
    assert total >= 1
    assert rows[0].beam_angle_deg is not None
    assert 5.0 <= float(rows[0].beam_angle_deg) <= 180.0


def test_duplicate_not_reindexed(tmp_path: Path):
    folder = _make_fixture_dir(tmp_path)
    db = tmp_path / "library.sqlite"
    with PhotometryLibrary(db) as lib:
        c1 = lib.index_directory(folder, recursive=True)
        c2 = lib.index_directory(folder, recursive=True)
        stats = lib.get_statistics()
    assert c1 == 3
    assert c2 == 0
    assert stats["total_files"] == 3


def test_get_statistics(tmp_path: Path):
    folder = _make_fixture_dir(tmp_path)
    db = tmp_path / "library.sqlite"
    with PhotometryLibrary(db) as lib:
        lib.index_directory(folder, recursive=True)
        stats = lib.get_statistics()
    assert stats["total_files"] == 3
    assert stats["manufacturers"] >= 2
    assert stats["format_breakdown"].get("IES", 0) == 3


def test_remove_missing(tmp_path: Path):
    folder = _make_fixture_dir(tmp_path)
    db = tmp_path / "library.sqlite"
    removed_name = folder / "b_spot.ies"
    with PhotometryLibrary(db) as lib:
        lib.index_directory(folder, recursive=True)
        removed_name.unlink()
        removed = lib.remove_missing_files()
        stats = lib.get_statistics()
    assert removed == 1
    assert stats["total_files"] == 2

