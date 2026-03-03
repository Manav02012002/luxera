from pathlib import Path

from luxera.export.layout_plan import LayoutPlanGenerator
from luxera.project.schema import LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def _sample_project(tmp_path: Path) -> Project:
    project = Project(name="Layout Plan Test", root_dir=str(tmp_path))
    project.geometry.rooms.append(RoomSpec(id="room-1", name="Room 1", width=6.0, length=4.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    project.photometry_assets.append(PhotometryAsset(id="asset-1", format="IES", metadata={"beam_angle_deg": 70.0}))
    project.luminaires.append(
        LuminaireInstance(
            id="lum-1",
            name="Luminaire 1",
            photometry_asset_id="asset-1",
            mounting_type="recessed_square",
            transform=TransformSpec(position=(2.0, 1.5, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    project.luminaires.append(
        LuminaireInstance(
            id="lum-2",
            name="Luminaire 2",
            photometry_asset_id="asset-1",
            mounting_type="downlight",
            transform=TransformSpec(position=(4.0, 2.5, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    return project


def test_rcp_svg_creates_file(tmp_path: Path) -> None:
    generator = LayoutPlanGenerator()
    project = _sample_project(tmp_path)
    out = tmp_path / "rcp.svg"
    generator.generate_rcp(project=project, output_format="svg", output_path=out)
    assert out.exists()
    text = out.read_text(encoding="utf-8", errors="replace").lower()
    assert "<svg" in text


def test_rcp_contains_luminaire_symbols(tmp_path: Path) -> None:
    generator = LayoutPlanGenerator()
    project = _sample_project(tmp_path)
    out = tmp_path / "rcp_symbols.svg"
    generator.generate_rcp(project=project, output_format="svg", output_path=out)
    text = out.read_text(encoding="utf-8", errors="replace")
    assert "luminaire-symbol" in text


def test_section_view(tmp_path: Path) -> None:
    generator = LayoutPlanGenerator()
    project = _sample_project(tmp_path)
    out = tmp_path / "section.svg"
    generator.generate_section(project=project, section_axis="x", section_position=0.5, output_format="svg", output_path=out)
    assert out.exists()


def test_luminaire_symbols() -> None:
    generator = LayoutPlanGenerator()
    for lum_type in ["recessed_square", "surface_mount", "pendant", "downlight", "linear"]:
        primitives = generator.generate_luminaire_symbol(lum_type)
        assert isinstance(primitives, list)
        assert len(primitives) > 0


def test_title_block(tmp_path: Path) -> None:
    generator = LayoutPlanGenerator()
    project = _sample_project(tmp_path)
    items = generator._draw_title_block(project, "1:100")
    assert any(str(project.name) in str(it.get("value", "")) for it in items)
