from __future__ import annotations

import math

from luxera.sports.analysis import SportsLightingAnalysis
from luxera.sports.en12193 import SPORT_STANDARDS
from luxera.sports.field import STANDARD_FIELDS
from luxera.sports.pole import PoleLayout


def test_standard_exists_football_class_i():
    std = SPORT_STANDARDS["football"]["I"]
    assert std.E_h_maintained == 500


def test_field_fifa_dimensions():
    f = STANDARD_FIELDS["football_fifa"]
    assert f.length == 105
    assert f.width == 68


def test_four_corner_layout():
    field = STANDARD_FIELDS["football_fifa"]
    poles = PoleLayout.four_corner(field, pole_height=25.0, offset=3.0)
    assert len(poles) == 4
    xs = sorted(p.position[0] for p in poles)
    ys = sorted(p.position[1] for p in poles)
    assert xs[0] < 0 < xs[-1]
    assert ys[0] < 0 < ys[-1]


def test_aiming_computation():
    field = STANDARD_FIELDS["football_fifa"]
    pole = PoleLayout.four_corner(field, pole_height=25.0, offset=3.0)[0]
    # override pole position for deterministic check
    pole.position = (0.0, 0.0, 25.0)
    tilt, rot = PoleLayout.compute_aiming(pole, (50.0, 30.0, 0.0))
    expected = math.degrees(math.atan2(25.0, math.hypot(50.0, 30.0)))
    assert abs(tilt - expected) < 1e-6
    assert 0.0 <= rot < 360.0


def test_sports_analysis_runs():
    field = STANDARD_FIELDS["football_fifa"]
    poles = PoleLayout.four_corner(field, pole_height=25.0, offset=3.0)
    result = SportsLightingAnalysis().run(
        field=field,
        poles=poles,
        standard=SPORT_STANDARDS["football"]["III"],
        grid_spacing=20.0,
    )
    assert result.E_h_avg > 0.0


def test_compliance_check_fields():
    field = STANDARD_FIELDS["football_fifa"]
    poles = PoleLayout.four_corner(field, pole_height=25.0, offset=3.0)
    result = SportsLightingAnalysis().run(
        field=field,
        poles=poles,
        standard=SPORT_STANDARDS["football"]["II"],
        grid_spacing=20.0,
    )
    assert "E_h_maintained" in result.compliance
    assert "E_h_uniformity_U1" in result.compliance
    assert "E_h_uniformity_U2" in result.compliance

