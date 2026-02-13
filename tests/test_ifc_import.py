from __future__ import annotations

import builtins
import types
import sys
from pathlib import Path

from luxera.io.ifc_import import IFCImportOptions, import_ifc


def test_import_ifc_counts_and_units() -> None:
    path = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = import_ifc(path, IFCImportOptions())
    assert len(out.rooms) == 2
    assert len(out.openings) == 1
    assert len(out.levels) == 1
    assert len(out.surfaces) >= 12
    assert out.openings[0].host_surface_id is not None
    assert float(out.coordinate_system.get("scale_to_meters", 0.0)) == 1.0
    assert str(out.coordinate_system.get("length_unit")) == "m"


def test_import_ifc_boundary_maps_window_to_target_space(monkeypatch) -> None:
    path = Path("tests/fixtures/ifc/simple_office_boundaries.ifc").resolve()

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name.startswith("ifcopenshell"):
            raise ImportError("blocked for fallback boundary test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    out = import_ifc(path, IFCImportOptions())
    assert out.openings
    # Boundary references #12 (second space), so host should map to ifc_space_2 wall.
    assert out.openings[0].host_surface_id == "ifc_space_2_wall_south"


def test_import_ifc_boundary_conflict_is_deterministic(monkeypatch) -> None:
    path = Path("tests/fixtures/ifc/simple_office_boundaries_conflict.ifc").resolve()

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name.startswith("ifcopenshell"):
            raise ImportError("blocked for fallback boundary conflict test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    out = import_ifc(path, IFCImportOptions())
    assert out.openings
    # Conflict #12 then #11 should still pick lower-index room (ifc_space_1).
    assert out.openings[0].host_surface_id == "ifc_space_1_wall_south"
    assert any("resolved deterministically" in w for w in out.warnings)


def test_import_ifc_geom_surfaces_get_room_ownership_from_boundaries(monkeypatch, tmp_path: Path) -> None:
    class _Entity:
        def __init__(self, sid: int, name: str = "", long_name: str = "") -> None:
            self._id = sid
            self.Name = name
            self.LongName = long_name

        def id(self) -> int:
            return self._id

        def is_a(self):  # noqa: ANN201
            return self.__class__.__name__.replace("_", "")

    class _IfcWall(_Entity):
        pass

    class _IfcSpace(_Entity):
        pass

    class _RelBoundary:
        def __init__(self, space, elem) -> None:
            self.RelatingSpace = space
            self.RelatedBuildingElement = elem

    class _Model:
        def __init__(self) -> None:
            self.space = _IfcSpace(11, name="Space A", long_name="Space A")
            self.wall = _IfcWall(101, name="Wall A")
            self.rel = _RelBoundary(self.space, self.wall)

        def by_type(self, name: str):  # noqa: ANN001
            if name == "IfcSpace":
                return [self.space]
            if name == "IfcWall":
                return [self.wall]
            if name == "IfcRelSpaceBoundary":
                return [self.rel]
            return []

    class _GeomShape:
        class geometry:  # noqa: N801
            verts = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
            faces = [0, 1, 2]

    ifc_mod = types.ModuleType("ifcopenshell")
    geom_mod = types.ModuleType("ifcopenshell.geom")
    ifc_mod.open = lambda path: _Model()  # noqa: ARG005
    geom_mod.settings = lambda: object()
    geom_mod.create_shape = lambda settings, ent: _GeomShape()  # noqa: ARG005
    ifc_mod.geom = geom_mod
    monkeypatch.setitem(sys.modules, "ifcopenshell", ifc_mod)
    monkeypatch.setitem(sys.modules, "ifcopenshell.geom", geom_mod)

    fixture = tmp_path / "mock.ifc"
    fixture.write_text("ISO-10303-21;ENDSEC;END-ISO-10303-21;", encoding="utf-8")
    out = import_ifc(fixture, IFCImportOptions())
    assert out.surfaces
    assert out.surfaces[0].room_id == "ifc_space_1"


def test_import_ifc_fallback_wall_surface_room_ownership(monkeypatch) -> None:
    path = Path("tests/fixtures/ifc/simple_office_wall_boundary.ifc").resolve()

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name.startswith("ifcopenshell"):
            raise ImportError("blocked for fallback wall boundary test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    out = import_ifc(path, IFCImportOptions())
    wall_surfaces = [s for s in out.surfaces if s.id.startswith("ifc_wall_")]
    assert wall_surfaces
    assert wall_surfaces[0].room_id == "ifc_space_2"


def test_import_ifc_fallback_wall_boundary_conflict_is_deterministic(monkeypatch) -> None:
    path = Path("tests/fixtures/ifc/simple_office_wall_boundary_conflict.ifc").resolve()

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name.startswith("ifcopenshell"):
            raise ImportError("blocked for fallback wall boundary conflict test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    out = import_ifc(path, IFCImportOptions())
    wall_surfaces = [s for s in out.surfaces if s.id.startswith("ifc_wall_")]
    assert wall_surfaces
    assert wall_surfaces[0].room_id == "ifc_space_1"
    assert any("ownership conflicts resolved deterministically" in w for w in out.warnings)


def test_import_ifc_fallback_slab_surface_room_ownership(monkeypatch) -> None:
    path = Path("tests/fixtures/ifc/simple_office_slab_boundary.ifc").resolve()

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name.startswith("ifcopenshell"):
            raise ImportError("blocked for fallback slab boundary test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    out = import_ifc(path, IFCImportOptions())
    slab_surfaces = [s for s in out.surfaces if s.id.startswith("ifc_slab_")]
    assert slab_surfaces
    assert slab_surfaces[0].room_id == "ifc_space_2"


def test_import_ifc_fallback_slab_boundary_conflict_is_deterministic(monkeypatch) -> None:
    path = Path("tests/fixtures/ifc/simple_office_slab_boundary_conflict.ifc").resolve()

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name.startswith("ifcopenshell"):
            raise ImportError("blocked for fallback slab boundary conflict test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    out = import_ifc(path, IFCImportOptions())
    slab_surfaces = [s for s in out.surfaces if s.id.startswith("ifc_slab_")]
    assert slab_surfaces
    assert slab_surfaces[0].room_id == "ifc_space_1"
    assert any("IFCSLAB" in w for w in out.warnings)
