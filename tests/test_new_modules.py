"""Tests for the new Luxera modules: geometry, compliance, emergency, project."""

import pytest
import tempfile
from pathlib import Path

# =============================================================================
# Geometry Tests
# =============================================================================

def test_vector3_operations():
    from luxera.geometry import Vector3
    
    v1 = Vector3(1, 2, 3)
    v2 = Vector3(4, 5, 6)
    
    # Addition
    v3 = v1 + v2
    assert v3.x == 5 and v3.y == 7 and v3.z == 9
    
    # Dot product
    dot = v1.dot(v2)
    assert dot == 1*4 + 2*5 + 3*6  # 32
    
    # Cross product
    cross = v1.cross(v2)
    assert cross.x == 2*6 - 3*5  # -3
    assert cross.y == 3*4 - 1*6  # 6
    assert cross.z == 1*5 - 2*4  # -3
    
    # Normalize
    v4 = Vector3(3, 4, 0)
    norm = v4.normalize()
    assert abs(norm.length() - 1.0) < 1e-10


def test_polygon_area():
    from luxera.geometry import Vector3, Polygon
    
    # Unit square
    square = Polygon([
        Vector3(0, 0, 0),
        Vector3(1, 0, 0),
        Vector3(1, 1, 0),
        Vector3(0, 1, 0),
    ])
    
    assert abs(square.get_area() - 1.0) < 1e-10
    
    # 2x3 rectangle
    rect = Polygon([
        Vector3(0, 0, 0),
        Vector3(2, 0, 0),
        Vector3(2, 3, 0),
        Vector3(0, 3, 0),
    ])
    
    assert abs(rect.get_area() - 6.0) < 1e-10


def test_polygon_normal():
    from luxera.geometry import Vector3, Polygon
    
    # Horizontal floor (normal should point up)
    floor = Polygon([
        Vector3(0, 0, 0),
        Vector3(1, 0, 0),
        Vector3(1, 1, 0),
        Vector3(0, 1, 0),
    ])
    
    normal = floor.get_normal()
    assert abs(normal.z - 1.0) < 0.01 or abs(normal.z + 1.0) < 0.01


def test_room_creation():
    from luxera.geometry import Room, MATERIALS
    
    room = Room.rectangular(
        name="Test Room",
        width=6.0,
        length=8.0,
        height=2.8,
    )
    
    assert abs(room.floor_area - 48.0) < 0.01
    assert abs(room.volume - 48.0 * 2.8) < 0.01
    
    surfaces = room.get_surfaces()
    # 1 floor + 1 ceiling + 4 walls = 6 surfaces
    assert len(surfaces) == 6


def test_material_library():
    from luxera.geometry import MATERIALS
    
    assert 'white_paint' in MATERIALS
    assert 'carpet_medium' in MATERIALS
    assert 'glass' in MATERIALS
    
    white = MATERIALS['white_paint']
    assert white.reflectance == 0.80


# =============================================================================
# Compliance Tests
# =============================================================================

def test_compliance_check_pass():
    from luxera.compliance import check_compliance, ActivityType
    
    report = check_compliance(
        room_name="Office A",
        activity_type=ActivityType.OFFICE_GENERAL,
        maintained_illuminance=550,  # Above 500 lux requirement
        uniformity=0.65,  # Above 0.6 requirement
    )
    
    assert report.is_compliant
    assert report.fail_count == 0


def test_compliance_check_fail():
    from luxera.compliance import check_compliance, ActivityType
    
    report = check_compliance(
        room_name="Office B",
        activity_type=ActivityType.OFFICE_GENERAL,
        maintained_illuminance=300,  # Below 500 lux requirement
        uniformity=0.4,  # Below 0.6 requirement
    )
    
    assert not report.is_compliant
    assert report.fail_count >= 2


def test_lighting_requirements():
    from luxera.compliance import get_requirement, ActivityType
    
    req = get_requirement(ActivityType.OFFICE_GENERAL)
    assert req.maintained_illuminance == 500
    assert req.uniformity_min == 0.6
    assert req.ugr_max == 19
    
    warehouse_req = get_requirement(ActivityType.WAREHOUSE_GENERAL)
    assert warehouse_req.maintained_illuminance == 100


def test_activity_types_list():
    from luxera.compliance import list_activity_types, ActivityType
    
    types = list_activity_types()
    assert len(types) > 10  # Should have many activity types
    
    # Check that we have common types
    type_names = [t[0] for t in types]
    assert ActivityType.OFFICE_GENERAL in type_names
    assert ActivityType.CLASSROOM in type_names


# =============================================================================
# Emergency Lighting Tests
# =============================================================================

def test_emergency_luminaire():
    from luxera.emergency import EmergencyLuminaire
    from luxera.geometry import Vector3
    
    lum = EmergencyLuminaire(
        position=Vector3(5, 5, 0),
        emergency_lumens=200,
        mounting_height=2.5,
    )
    
    # Intensity at nadir should be highest
    I_nadir = lum.get_intensity_at_angle(0)
    I_45 = lum.get_intensity_at_angle(45)
    
    assert I_nadir > I_45


def test_escape_route():
    from luxera.emergency import EscapeRoute
    from luxera.geometry import Vector3
    
    route = EscapeRoute(
        name="Main Corridor",
        centerline_points=[
            Vector3(0, 0, 0),
            Vector3(10, 0, 0),
            Vector3(10, 5, 0),
        ],
        width=2.0,
    )
    
    assert abs(route.length - 15.0) < 0.01
    
    samples = route.get_sample_points(spacing=2.0)
    assert len(samples) >= 7


def test_emergency_calculation():
    from luxera.emergency import (
        EmergencyLuminaire, 
        EscapeRoute, 
        calculate_escape_route
    )
    from luxera.geometry import Vector3
    
    # Create a simple route
    route = EscapeRoute(
        name="Test Route",
        centerline_points=[
            Vector3(0, 0, 0),
            Vector3(10, 0, 0),
        ],
        width=2.0,
    )
    
    # Place luminaires along the route
    luminaires = [
        EmergencyLuminaire(
            position=Vector3(2.5, 0, 0),
            emergency_lumens=200,
            mounting_height=2.5,
        ),
        EmergencyLuminaire(
            position=Vector3(7.5, 0, 0),
            emergency_lumens=200,
            mounting_height=2.5,
        ),
    ]
    
    result = calculate_escape_route(route, luminaires)
    
    assert result.min_lux > 0
    assert result.max_lux > result.min_lux


def test_luminaire_spacing_suggestion():
    from luxera.emergency import suggest_luminaire_spacing
    
    spacing = suggest_luminaire_spacing(
        min_lux=1.0,
        mounting_height=2.5,
        luminaire_lumens=200,
    )
    
    # Should be a reasonable spacing (2-15m range)
    assert 2.0 <= spacing <= 15.0


# =============================================================================
# Project File Tests
# =============================================================================

def test_create_project():
    from luxera.project import create_new_project
    
    project = create_new_project(
        name="Test Project",
        author="Test Author",
        company="Test Company",
    )
    
    assert project.metadata.name == "Test Project"
    assert project.metadata.author == "Test Author"
    assert len(project.rooms) == 0
    assert len(project.luminaires) == 0


def test_add_room_to_project():
    from luxera.project import create_new_project
    from luxera.geometry import Room
    
    project = create_new_project(name="Test")
    
    room = Room.rectangular(
        name="Office",
        width=6.0,
        length=8.0,
        height=2.8,
    )
    
    room_id = project.add_room(room)
    
    assert len(project.rooms) == 1
    assert project.rooms[0].name == "Office"
    assert project.rooms[0].height == 2.8


def test_project_save_load():
    from luxera.project import create_new_project, save_project, load_project
    from luxera.geometry import Room
    
    # Create project
    project = create_new_project(name="Save Test")
    room = Room.rectangular("Room1", 5, 5, 3)
    project.add_room(room)
    project.notes = "Test notes"
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix='.luxera', delete=False) as f:
        filepath = Path(f.name)
    
    try:
        save_project(project, filepath)
        
        # Load back
        loaded = load_project(filepath)
        
        assert loaded.metadata.name == "Save Test"
        assert len(loaded.rooms) == 1
        assert loaded.rooms[0].name == "Room1"
        assert loaded.notes == "Test notes"
    finally:
        filepath.unlink()


def test_office_project_template():
    from luxera.project import create_office_project
    
    project = create_office_project(
        name="New Office",
        room_width=8.0,
        room_length=10.0,
        room_height=3.0,
    )
    
    assert len(project.rooms) == 1
    assert project.rooms[0].height == 3.0
    assert project.calculation_settings.work_plane_height == 0.8


# =============================================================================
# Radiosity Tests
# =============================================================================

def test_form_factor_calculation():
    from luxera.calculation.radiosity import compute_form_factor_analytic
    from luxera.geometry import Vector3, Polygon, Surface, Material
    
    # Two parallel patches facing each other
    mat = Material("test", reflectance=0.5)
    
    patch1 = Surface(
        id="patch1",
        polygon=Polygon([
            Vector3(0, 0, 0),
            Vector3(1, 0, 0),
            Vector3(1, 1, 0),
            Vector3(0, 1, 0),
        ]),
        material=mat,
    )
    
    patch2 = Surface(
        id="patch2",
        polygon=Polygon([
            Vector3(0, 0, 2),
            Vector3(0, 1, 2),
            Vector3(1, 1, 2),
            Vector3(1, 0, 2),
        ]),
        material=mat,
    )
    
    F = compute_form_factor_analytic(patch1, patch2)
    
    # Form factor should be positive and less than 1
    assert 0 < F < 1


def test_radiosity_solver():
    from luxera.calculation.radiosity import RadiositySolver, RadiositySettings
    from luxera.geometry import Room
    
    room = Room.rectangular("Test", 4, 4, 3)
    surfaces = room.get_surfaces()
    
    # Set some direct illuminance
    direct = {
        "Test_floor": 500.0,
    }
    
    settings = RadiositySettings(
        max_iterations=10,
        patch_max_area=2.0,
    )
    
    solver = RadiositySolver(settings)
    result = solver.solve(surfaces, direct)
    
    assert len(result.patches) > 0
    assert result.iterations > 0


# =============================================================================
# DXF Import Tests
# =============================================================================

def test_dxf_parser():
    from luxera.io import DXFParser
    
    # Minimal DXF content
    dxf_content = """0
SECTION
2
ENTITIES
0
LINE
8
WALLS
10
0.0
20
0.0
11
10.0
21
0.0
0
ENDSEC
0
EOF
"""
    
    parser = DXFParser()
    doc = parser.parse_string(dxf_content)
    
    # Should have parsed something
    assert doc is not None
