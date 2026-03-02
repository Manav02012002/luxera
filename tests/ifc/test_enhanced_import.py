from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from luxera.ifc.enhanced_importer import EnhancedIFCImporter


class _FakeEntity:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeModel:
    def __init__(self):
        self._spaces = [
            _FakeEntity(
                GlobalId="SPACE_1",
                Name="Open Office",
                LongName="Open Plan Office",
                Width=12.0,
                Length=8.0,
                Height=3.0,
                Origin=(0.0, 0.0, 0.0),
            )
        ]
        self._walls = [
            _FakeEntity(GlobalId="WALL_1", Name="Wall 1", Width=8.0, Height=3.0, Origin=(0.0, 0.0, 0.0), Material="Concrete"),
            _FakeEntity(GlobalId="WALL_2", Name="Wall 2", Width=8.0, Height=3.0, Origin=(12.0, 0.0, 0.0), Material="Plaster"),
        ]
        self._slabs = [
            _FakeEntity(GlobalId="SLAB_1", Name="Floor", Width=12.0, Length=8.0, Height=0.2, Origin=(0.0, 0.0, 0.0), Material="Carpet")
        ]
        self._roofs = [
            _FakeEntity(GlobalId="ROOF_1", Name="Ceiling", Width=12.0, Length=8.0, Height=0.2, Origin=(0.0, 0.0, 2.9), Material="Gypsum")
        ]
        self._windows = [
            _FakeEntity(GlobalId="WIN_1", Name="Window 1", OverallWidth=1.5, OverallHeight=1.2, Origin=(2.0, 0.0, 1.0), HostSurfaceId="WALL_1")
        ]
        self._doors = [
            _FakeEntity(GlobalId="DOOR_1", Name="Door 1", OverallWidth=0.9, OverallHeight=2.1, Origin=(0.0, 3.0, 0.0), HostSurfaceId="WALL_2")
        ]
        self._storeys = [_FakeEntity(GlobalId="L1", Name="Level 1", Elevation=0.0)]

    def by_type(self, name: str):
        return {
            "IfcSpace": self._spaces,
            "IfcWall": self._walls,
            "IfcSlab": self._slabs,
            "IfcRoof": self._roofs,
            "IfcWindow": self._windows,
            "IfcDoor": self._doors,
            "IfcBuildingStorey": self._storeys,
        }.get(name, [])


def _install_fake_ifcopenshell(monkeypatch, model: _FakeModel) -> None:
    fake_mod = types.SimpleNamespace(open=lambda _: model)
    monkeypatch.setitem(sys.modules, "ifcopenshell", fake_mod)


def test_space_extraction(tmp_path: Path, monkeypatch) -> None:
    model = _FakeModel()
    _install_fake_ifcopenshell(monkeypatch, model)
    f = tmp_path / "sample.ifc"
    f.write_text("ISO-10303-21;", encoding="utf-8")

    imp = EnhancedIFCImporter(f)
    spaces = imp.import_spaces()

    assert spaces
    assert spaces[0]["name"] == "Open Office"
    assert spaces[0]["width"] == pytest.approx(12.0)
    assert spaces[0]["length"] == pytest.approx(8.0)
    assert spaces[0]["height"] == pytest.approx(3.0)


def test_material_reflectance_estimation(tmp_path: Path, monkeypatch) -> None:
    _install_fake_ifcopenshell(monkeypatch, _FakeModel())
    f = tmp_path / "sample.ifc"
    f.write_text("ISO-10303-21;", encoding="utf-8")
    imp = EnhancedIFCImporter(f)

    assert imp._estimate_reflectance("Concrete C30") == pytest.approx(0.35)
    assert imp._estimate_reflectance("Gypsum Board") == pytest.approx(0.70)
    assert imp._estimate_reflectance("Wood Veneer") == pytest.approx(0.30)


def test_unknown_material_default(tmp_path: Path, monkeypatch) -> None:
    _install_fake_ifcopenshell(monkeypatch, _FakeModel())
    f = tmp_path / "sample.ifc"
    f.write_text("ISO-10303-21;", encoding="utf-8")
    imp = EnhancedIFCImporter(f)
    assert imp._estimate_reflectance("SpaceAgeFoam") == pytest.approx(0.50)


def test_opening_detection(tmp_path: Path, monkeypatch) -> None:
    _install_fake_ifcopenshell(monkeypatch, _FakeModel())
    f = tmp_path / "sample.ifc"
    f.write_text("ISO-10303-21;", encoding="utf-8")
    imp = EnhancedIFCImporter(f)
    openings = imp.import_openings()

    assert any(o["kind"] == "window" for o in openings)
    assert any(o["kind"] == "door" for o in openings)


def test_to_project_structure(tmp_path: Path, monkeypatch) -> None:
    _install_fake_ifcopenshell(monkeypatch, _FakeModel())
    f = tmp_path / "sample.ifc"
    f.write_text("ISO-10303-21;", encoding="utf-8")
    imp = EnhancedIFCImporter(f)
    project = imp.to_project()

    assert project.geometry.rooms
    assert project.geometry.surfaces
    assert project.geometry.openings
    assert project.materials


def test_import_without_ifcopenshell(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "ifcopenshell", None)
    f = tmp_path / "sample.ifc"
    f.write_text("ISO-10303-21;", encoding="utf-8")

    with pytest.raises(ImportError) as e:
        EnhancedIFCImporter(f)
    assert "pip install ifcopenshell" in str(e.value)
