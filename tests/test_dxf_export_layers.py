from __future__ import annotations

from pathlib import Path

from luxera.geometry.views.project import DrawingPrimitive
from luxera.io.dxf_export_pro import SymbolInsert, export_view_linework_to_dxf


def test_dxf_export_pro_writes_layers_and_symbols(tmp_path: Path) -> None:
    prims = [
        DrawingPrimitive(type="line", points=[(0.0, 0.0), (1.0, 0.0)], layer="CUT", style="solid", depth=0.0),
        DrawingPrimitive(type="polyline", points=[(0.0, 1.0), (1.0, 1.0), (1.0, 2.0)], layer="WALLS", style="solid", depth=0.0),
    ]
    syms = [SymbolInsert(block="LUM_SYMBOL", point=(0.5, 0.5), scale=1.0, layer="LUMINAIRES")]

    out = export_view_linework_to_dxf(prims, tmp_path / "plan_pro.dxf", symbols=syms, layer_map={"CUT": "A-CUT", "WALLS": "A-WALL"})
    text = out.read_text(encoding="utf-8")

    assert "SECTION" in text
    assert "TABLES" in text
    assert "LAYER" in text
    assert "2\nA-CUT\n" in text
    assert "2\nA-WALL\n" in text
    assert "2\nLUMINAIRES\n" in text
    assert "BLOCKS" in text
    assert "LUM_SYMBOL" in text
    assert "INSERT" in text
