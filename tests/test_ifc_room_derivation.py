from __future__ import annotations

import builtins
from pathlib import Path

from luxera.io.ifc_import import IFCImportOptions, import_ifc


def test_ifc_derives_rooms_from_walls_when_ifcspace_missing(monkeypatch, tmp_path: Path) -> None:
    fixture = tmp_path / "walls_only.ifc"
    fixture.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "#1 = IFCWALL('w1');",
                "#2 = IFCWALL('w2');",
                "#3 = IFCWALL('w3');",
                "#4 = IFCWALL('w4');",
                "ENDSEC;",
                "END-ISO-10303-21;",
            ]
        ),
        encoding="utf-8",
    )

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name.startswith("ifcopenshell"):
            raise ImportError("blocked for wall-derived rooms test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    out = import_ifc(fixture, IFCImportOptions())
    assert out.rooms
    assert out.rooms[0].id.startswith("ifc_derived_room_")
    floor = [s for s in out.surfaces if s.kind == "floor" and s.room_id == out.rooms[0].id]
    ceiling = [s for s in out.surfaces if s.kind == "ceiling" and s.room_id == out.rooms[0].id]
    assert floor and ceiling
    assert any("derived room envelopes" in w for w in out.warnings)
