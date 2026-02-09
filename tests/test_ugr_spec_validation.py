import math

from luxera.calculation.ugr import calculate_guth_position_index, calculate_solid_angle, LuminaireForUGR
from luxera.geometry.core import Vector3


def test_guth_position_index_monotonic():
    p0 = calculate_guth_position_index(0, 0.1)
    p1 = calculate_guth_position_index(10, 0.1)
    p2 = calculate_guth_position_index(10, 30)
    assert p1 >= p0
    assert p2 >= 1.0


def test_guth_position_index_expected_value():
    # Compare to the implemented formula for a known case
    H = 10
    T = 20
    if T < 0.1:
        T = 0.1
    sigma = 1.0 + 0.5 * math.radians(abs(T))
    exponent = (35.2 - 0.31889 * abs(T) - 1.22 * math.exp(-abs(T) / 9)) * 1e-3 * (abs(H) + sigma)
    expected = math.exp(exponent)
    expected = max(1.0, min(expected, 100.0))

    actual = calculate_guth_position_index(10, 20)
    assert actual == expected


def test_solid_angle_simple():
    lum = LuminaireForUGR(position=Vector3(0, 0, 3), luminous_area=1.0, luminance=1000)
    observer = Vector3(0, 0, 0)
    omega = calculate_solid_angle(lum, observer)
    # For a 1 m^2 area at 3m distance, omega ~= A/d^2
    assert omega == (1.0 / 9.0)
