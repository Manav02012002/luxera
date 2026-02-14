from __future__ import annotations

from pathlib import Path

from luxera.geometry.views.project import DrawingPrimitive
from luxera.io.dxf_export_pro import SymbolInsert, export_view_linework_to_dxf


def test_dxf_export_pro_writes_layers_and_symbols(tmp_path: Path) -> None:
    prims = [
        DrawingPrimitive(type="line", points=[(0.0, 0.0), (1.0, 0.0)], layer="CUT", style="solid", depth=0.0),
        DrawingPrimitive(
            type="polyline",
            points=[(0.0, 1.0), (1.0, 1.0), (1.0, 2.0)],
            bulges=[0.25, 0.0, 0.0],
            layer="WALLS",
            style="solid",
            depth=0.0,
        ),
    ]
    syms = [
        SymbolInsert(block="LUM_SYMBOL", point=(0.5, 0.5), scale=1.0, layer="LUMINAIRES"),
        SymbolInsert(block="B_EXIT", point=(1.5, 0.5), scale=1.0, layer="LUMINAIRES"),
    ]

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
    assert "B_EXIT" in text
    assert "INSERT" in text
    assert "42\n0.25\n" in text


def test_dxf_export_pro_writes_text_primitive(tmp_path: Path) -> None:
    prims = [
        DrawingPrimitive(type="text", points=[(2.0, 3.0)], layer="ANNOT", style="solid", depth=0.0, text="A1"),
    ]
    out = export_view_linework_to_dxf(prims, tmp_path / "plan_text.dxf", symbols=[], layer_map={"ANNOT": "A-ANNO"})
    text = out.read_text(encoding="utf-8")
    assert "TEXT" in text
    assert "2\nA-ANNO\n" in text
    assert "1\nA1\n" in text
