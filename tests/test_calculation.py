"""Tests for the illuminance calculation module."""

import pytest
import math

from luxera.parser.ies_parser import parse_ies_text
from luxera.calculation.illuminance import (
    Point3D,
    Luminaire,
    CalculationGrid,
    calculate_direct_illuminance,
    calculate_grid_illuminance,
    interpolate_candela,
    quick_room_calculation,
)


# Simple test IES data with known candela values
TEST_IES = """IESNA:LM-63-2002
[MANUFAC] Test
TILT=NONE
1 1000 1 5 1 1 2 0.1 0.1 0.05
0 30 60 90 120
0
1000 900 700 400 100
"""


def test_point3d_operations():
    p1 = Point3D(1, 2, 3)
    p2 = Point3D(4, 5, 6)
    
    # Addition
    p3 = p1 + p2
    assert p3.x == 5 and p3.y == 7 and p3.z == 9
    
    # Subtraction
    p4 = p2 - p1
    assert p4.x == 3 and p4.y == 3 and p4.z == 3
    
    # Length
    p5 = Point3D(3, 4, 0)
    assert abs(p5.length() - 5.0) < 1e-10
    
    # Normalize
    p6 = Point3D(0, 0, 2).normalize()
    assert abs(p6.z - 1.0) < 1e-10


def test_interpolate_candela():
    doc = parse_ies_text(TEST_IES)
    
    # At exact angle
    cd_0 = interpolate_candela(doc, 0, 0)
    assert abs(cd_0 - 1000) < 1
    
    cd_30 = interpolate_candela(doc, 30, 0)
    assert abs(cd_30 - 900) < 1
    
    # Interpolated
    cd_15 = interpolate_candela(doc, 15, 0)
    assert 900 < cd_15 < 1000


def test_direct_illuminance_under_luminaire():
    """Test illuminance directly under a point source."""
    doc = parse_ies_text(TEST_IES)
    
    # Luminaire at height 3m
    luminaire = Luminaire(
        position=Point3D(0, 0, 3),
        ies_data=doc,
    )
    
    # Point directly under luminaire at floor
    point = Point3D(0, 0, 0)
    normal = Point3D(0, 0, 1)  # Facing up
    
    E = calculate_direct_illuminance(point, normal, luminaire)
    
    # At nadir (gamma=0), I=1000cd, distance=3m
    # E = 1000 * cos(0) / 3^2 = 1000/9 ≈ 111 lux
    expected = 1000 / 9
    assert abs(E - expected) < 5  # Allow some tolerance


def test_illuminance_decreases_with_distance():
    """Verify inverse square law."""
    doc = parse_ies_text(TEST_IES)
    
    luminaire = Luminaire(
        position=Point3D(0, 0, 3),
        ies_data=doc,
    )
    
    normal = Point3D(0, 0, 1)
    
    E_close = calculate_direct_illuminance(Point3D(0, 0, 1), normal, luminaire)
    E_far = calculate_direct_illuminance(Point3D(0, 0, 0), normal, luminaire)
    
    # Closer point should have higher illuminance
    assert E_close > E_far


def test_illuminance_at_angle():
    """Test illuminance at off-nadir angles."""
    doc = parse_ies_text(TEST_IES)
    
    luminaire = Luminaire(
        position=Point3D(0, 0, 3),
        ies_data=doc,
    )
    
    normal = Point3D(0, 0, 1)
    
    # At 60° off nadir, intensity should be lower
    # At distance 3m, horizontal offset gives angle
    E_center = calculate_direct_illuminance(Point3D(0, 0, 0), normal, luminaire)
    E_offset = calculate_direct_illuminance(Point3D(3, 0, 0), normal, luminaire)
    
    assert E_offset < E_center


def test_calculation_grid():
    grid = CalculationGrid(
        origin=Point3D(0, 0, 0),
        width=10,
        height=8,
        elevation=0.8,
        nx=5,
        ny=4,
    )
    
    points = grid.get_points()
    assert len(points) == 20
    
    # Check corners
    p00 = grid.get_point(0, 0)
    assert p00.x == 0 and p00.y == 0 and p00.z == 0.8
    
    p44 = grid.get_point(4, 3)
    assert p44.x == 10 and p44.y == 8 and p44.z == 0.8


def test_grid_illuminance_calculation():
    """Test full grid calculation."""
    doc = parse_ies_text(TEST_IES)
    
    luminaire = Luminaire(
        position=Point3D(2, 2, 3),
        ies_data=doc,
    )
    
    grid = CalculationGrid(
        origin=Point3D(0, 0, 0),
        width=4,
        height=4,
        elevation=0,
        nx=5,
        ny=5,
    )
    
    result = calculate_grid_illuminance(grid, [luminaire])
    
    assert result.values.shape == (5, 5)
    assert result.max_lux > 0
    assert result.min_lux >= 0
    assert result.mean_lux > 0
    assert 0 <= result.uniformity_ratio <= 1


def test_quick_room_calculation():
    """Test the convenience function."""
    doc = parse_ies_text(TEST_IES)
    
    result = quick_room_calculation(
        ies_data=doc,
        room_width=4,
        room_length=4,
        mounting_height=2.5,
        work_plane_height=0.8,
        num_luminaires_x=2,
        num_luminaires_y=2,
    )
    
    assert result.max_lux > 0
    assert result.mean_lux > 0


def test_ldt_parser_import():
    """Test that LDT parser can be imported."""
    from luxera.parser.ldt_parser import parse_ldt_text, ParsedLDT
    assert callable(parse_ldt_text)


def test_advanced_validation_rules():
    """Test that advanced validation rules can be loaded."""
    from luxera.validation.defaults import default_validator
    
    validator = default_validator()
    assert len(validator.rules) > 4  # More than basic rules
