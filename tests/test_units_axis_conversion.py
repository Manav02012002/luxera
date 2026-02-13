from __future__ import annotations

import numpy as np

from luxera.core.coordinates import AxisConvention, axis_conversion_matrix, describe_axis_conversion
from luxera.core.units import parse_length


def test_parse_length_preserves_original_unit_metadata() -> None:
    p = parse_length(10.0, "ft")
    assert abs(p.value_m - 3.048) < 1e-12
    assert p.original_unit == "ft"
    assert p.original_value == 10.0


def test_axis_conversion_yup_left_to_canonical() -> None:
    report = describe_axis_conversion(AxisConvention(up_axis="Y_UP", handedness="LEFT_HANDED"))
    m = np.array(report.matrix, dtype=float)
    assert m.shape == (4, 4)
    assert "Y_UP/LEFT_HANDED->Z_UP/RIGHT_HANDED" in report.axis_transform_applied
    direct = axis_conversion_matrix(AxisConvention(up_axis="Y_UP", handedness="LEFT_HANDED"))
    assert np.allclose(m, direct)

