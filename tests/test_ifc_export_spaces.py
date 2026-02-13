from __future__ import annotations

from pathlib import Path

from luxera.io.ifc_export import export_ifc_spaces_and_luminaires
from luxera.project.schema import LuminaireInstance, Project, RoomSpec, RotationSpec, TransformSpec


def test_ifc_export_minimal_spaces_and_luminaires(tmp_path: Path) -> None:
    p = Project(name="ifc-export")
    p.geometry.rooms.append(RoomSpec(id="r1", name="Room 1", width=4.0, length=3.0, height=2.8))
    p.luminaires.append(
        LuminaireInstance(
            id="lum1",
            name="Luminaire 1",
            photometry_asset_id="asset1",
            transform=TransformSpec(position=(2.0, 1.5, 2.6), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )

    out = export_ifc_spaces_and_luminaires(p, tmp_path / "model.ifc")
    text = out.read_text(encoding="utf-8")

    assert "ISO-10303-21" in text
    assert "IFC4" in text
    assert "IFCSPACE" in text
    assert "IFCLIGHTFIXTURE" in text
    assert "Room 1" in text
    assert "Luminaire 1" in text
