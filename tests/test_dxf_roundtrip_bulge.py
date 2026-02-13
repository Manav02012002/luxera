from __future__ import annotations

from pathlib import Path

from luxera.io.dxf_roundtrip import load_roundtrip_dxf, roundtrip_dxf


def _sample_dxf() -> str:
    return """0
SECTION
2
HEADER
0
ENDSEC
0
SECTION
2
ENTITIES
0
LWPOLYLINE
8
A-WALL
90
2
70
0
10
0.0
20
0.0
42
0.5
10
2.0
20
0.0
0
LINE
8
A-AXIS
10
0.0
20
1.0
11
2.0
21
1.0
0
ENDSEC
0
EOF
"""


def test_dxf_roundtrip_preserves_bulges_and_layers(tmp_path: Path) -> None:
    src = tmp_path / "in.dxf"
    dst = tmp_path / "out.dxf"
    src.write_text(_sample_dxf(), encoding="utf-8")

    first = load_roundtrip_dxf(src)
    assert len(first.polylines) == 1
    assert first.polylines[0].layer == "A-WALL"
    assert first.polylines[0].bulges[0] == 0.5
    assert len(first.lines) == 1
    assert first.lines[0].layer == "A-AXIS"

    roundtrip_dxf(src, dst)

    second = load_roundtrip_dxf(dst)
    assert len(second.polylines) == 1
    assert second.polylines[0].layer == "A-WALL"
    assert abs(second.polylines[0].bulges[0] - 0.5) < 1e-12
    assert len(second.lines) == 1
    assert second.lines[0].layer == "A-AXIS"

    text = dst.read_text(encoding="utf-8")
    assert "LWPOLYLINE" in text
    assert "8\nA-WALL\n" in text
    assert "42\n0.5\n" in text
