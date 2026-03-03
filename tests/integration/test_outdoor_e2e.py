from __future__ import annotations

from pathlib import Path

from luxera.exterior.area_lighting import ExteriorAreaEngine, ExteriorAreaSpec, PoleSpec
from luxera.exterior.standards import check_exterior_compliance
from luxera.project.schema import PhotometryAsset, Project
from luxera.sports.analysis import SportsLightingAnalysis
from luxera.sports.en12193 import SPORT_STANDARDS
from luxera.sports.field import STANDARD_FIELDS
from luxera.sports.pole import PoleLayout


def _write_exterior_ies(tmp_path: Path) -> Path:
    ies = tmp_path / "exterior_fixture.ies"
    ies.write_text(
        """IESNA:LM-63-2002
TILT=NONE
1 24000 1 7 1 1 2 0.6 0.6 0.2
0 15 30 45 60 75 90
0
150000 140000 120000 95000 65000 25000 0
""",
        encoding="utf-8",
    )
    return ies


def _build_exterior_project(tmp_path: Path) -> Project:
    project = Project(name="Outdoor E2E", root_dir=str(tmp_path))
    ies = _write_exterior_ies(tmp_path)
    project.photometry_assets.append(PhotometryAsset(id="pole_asset", format="IES", path=str(ies)))
    return project


class TestOutdoorE2E:
    def test_parking_lot_basic(self, tmp_path: Path) -> None:
        """
        50x30m parking lot, 4 poles at 10m height, EN 12464-2.
        """
        project = _build_exterior_project(tmp_path)
        area = ExteriorAreaSpec(
            name="Parking Lot",
            boundary_polygon=[(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 30.0)],
            grid_spacing=5.0,
            grid_height=0.0,
        )
        poles = [
            PoleSpec(id="P1", position=(0.0, 0.0, 10.0), luminaire_asset_id="pole_asset", luminaire_count=1),
            PoleSpec(id="P2", position=(50.0, 0.0, 10.0), luminaire_asset_id="pole_asset", luminaire_count=1),
            PoleSpec(id="P3", position=(50.0, 30.0, 10.0), luminaire_asset_id="pole_asset", luminaire_count=1),
            PoleSpec(id="P4", position=(0.0, 30.0, 10.0), luminaire_asset_id="pole_asset", luminaire_count=1),
        ]

        result = ExteriorAreaEngine().compute(area, poles, project)
        checks = check_exterior_compliance(result, "parking_general")

        assert result["E_avg"] > 0.0
        assert "grid_points" in result and "values_flat" in result
        assert isinstance(checks, dict)
        assert "compliant" in checks

    def test_sports_field_four_pole(self) -> None:
        """
        Football field, 4-corner pole layout, EN 12193 Class III.
        """
        field = STANDARD_FIELDS["football_fifa"]
        poles = PoleLayout.four_corner(field, pole_height=25.0, offset=5.0)
        std = SPORT_STANDARDS["football"]["III"]

        result = SportsLightingAnalysis().run(field=field, poles=poles, standard=std, grid_spacing=10.0)

        assert result.E_h_avg > 0.0
        assert isinstance(result.compliance, dict)
        assert "E_h_maintained" in result.compliance
