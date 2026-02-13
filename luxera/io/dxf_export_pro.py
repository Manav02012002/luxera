from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from luxera.geometry.drafting import grid_linework_xy, luminaire_symbol_inserts, project_plan_view
from luxera.geometry.views.project import DrawingPrimitive
from luxera.project.schema import Project

Point2 = Tuple[float, float]


@dataclass(frozen=True)
class SymbolInsert:
    block: str
    point: Point2
    scale: float = 1.0
    rotation_deg: float = 0.0
    layer: str = "LUMINAIRES"


def _f(v: float) -> str:
    return f"{float(v):.12g}"


def _line_entity(a: Point2, b: Point2, layer: str) -> str:
    return (
        "0\nLINE\n"
        f"8\n{layer}\n"
        f"10\n{_f(a[0])}\n20\n{_f(a[1])}\n30\n0.0\n"
        f"11\n{_f(b[0])}\n21\n{_f(b[1])}\n31\n0.0\n"
    )


def _lwpolyline_entity(points: Sequence[Point2], layer: str, closed: bool = False) -> str:
    if len(points) < 2:
        return ""
    out = (
        "0\nLWPOLYLINE\n"
        f"8\n{layer}\n"
        f"90\n{len(points)}\n"
        f"70\n{1 if closed else 0}\n"
    )
    for x, y in points:
        out += f"10\n{_f(x)}\n20\n{_f(y)}\n"
    return out


def _arc_entity(center: Point2, start: Point2, end: Point2, layer: str) -> str:
    sx, sy = float(start[0]) - float(center[0]), float(start[1]) - float(center[1])
    ex, ey = float(end[0]) - float(center[0]), float(end[1]) - float(center[1])
    r = (sx * sx + sy * sy) ** 0.5
    sa = degrees(atan2(sy, sx))
    ea = degrees(atan2(ey, ex))
    return (
        "0\nARC\n"
        f"8\n{layer}\n"
        f"10\n{_f(center[0])}\n20\n{_f(center[1])}\n30\n0.0\n"
        f"40\n{_f(r)}\n"
        f"50\n{_f(sa)}\n"
        f"51\n{_f(ea)}\n"
    )


def _insert_entity(sym: SymbolInsert) -> str:
    return (
        "0\nINSERT\n"
        f"8\n{sym.layer}\n"
        f"2\n{sym.block}\n"
        f"10\n{_f(sym.point[0])}\n20\n{_f(sym.point[1])}\n30\n0.0\n"
        f"41\n{_f(sym.scale)}\n42\n{_f(sym.scale)}\n43\n{_f(sym.scale)}\n"
        f"50\n{_f(sym.rotation_deg)}\n"
    )


def _block_luminaire_symbol(name: str = "LUM_SYMBOL") -> str:
    return (
        "0\nBLOCK\n8\n0\n"
        f"2\n{name}\n"
        "70\n0\n10\n0.0\n20\n0.0\n30\n0.0\n"
        "0\nCIRCLE\n8\nLUMINAIRES\n10\n0.0\n20\n0.0\n30\n0.0\n40\n0.25\n"
        "0\nLINE\n8\nLUMINAIRES\n10\n-0.3\n20\n0.0\n30\n0.0\n11\n0.3\n21\n0.0\n31\n0.0\n"
        "0\nLINE\n8\nLUMINAIRES\n10\n0.0\n20\n-0.3\n30\n0.0\n11\n0.0\n21\n0.3\n31\n0.0\n"
        "0\nENDBLK\n"
    )


def _layer_table(layers: Iterable[str]) -> str:
    unique = sorted({str(x) for x in layers if str(x)})
    out = "0\nTABLE\n2\nLAYER\n70\n0\n"
    for lay in unique:
        out += "0\nLAYER\n"
        out += f"2\n{lay}\n70\n0\n62\n7\n6\nCONTINUOUS\n"
    out += "0\nENDTAB\n"
    return out


def export_view_linework_to_dxf(
    primitives: Sequence[DrawingPrimitive],
    out_path: str | Path,
    *,
    symbols: Sequence[SymbolInsert] = (),
    layer_map: Mapping[str, str] | None = None,
) -> Path:
    lm = dict(layer_map or {})

    entities: List[str] = []
    used_layers: List[str] = ["0"]

    for p in primitives:
        lay = str(lm.get(p.layer, p.layer))
        used_layers.append(lay)
        pts = [(float(x), float(y)) for x, y in p.points]
        if p.type == "line" and len(pts) >= 2:
            entities.append(_line_entity(pts[0], pts[1], lay))
        elif p.type == "polyline" and len(pts) >= 2:
            entities.append(_lwpolyline_entity(pts, lay, closed=False))
        elif p.type == "arc" and len(pts) >= 3:
            entities.append(_arc_entity(pts[0], pts[1], pts[2], lay))

    for s in symbols:
        mapped = SymbolInsert(
            block=s.block,
            point=(float(s.point[0]), float(s.point[1])),
            scale=float(s.scale),
            rotation_deg=float(s.rotation_deg),
            layer=str(lm.get(s.layer, s.layer)),
        )
        used_layers.append(mapped.layer)
        entities.append(_insert_entity(mapped))

    content = "0\nSECTION\n2\nHEADER\n0\nENDSEC\n"
    content += "0\nSECTION\n2\nTABLES\n"
    content += _layer_table(used_layers)
    content += "0\nENDSEC\n"
    content += "0\nSECTION\n2\nBLOCKS\n"
    content += _block_luminaire_symbol("LUM_SYMBOL")
    content += "0\nENDSEC\n"
    content += "0\nSECTION\n2\nENTITIES\n"
    content += "".join(entities)
    content += "0\nENDSEC\n0\nEOF\n"

    out = Path(out_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return out


def export_plan_to_dxf_pro(
    project: Project,
    out_path: str | Path,
    *,
    cut_z: float,
    include_grids: bool = True,
    include_luminaires: bool = True,
    layer_map: Mapping[str, str] | None = None,
) -> Path:
    proj = project_plan_view(project.geometry.surfaces, cut_z=float(cut_z), include_below=True)
    prims: List[DrawingPrimitive] = []

    for a, b in proj.silhouettes:
        prims.append(DrawingPrimitive(type="line", points=[a, b], layer="WALLS", style="solid", depth=0.0))
    for a, b in proj.cut_segments:
        prims.append(DrawingPrimitive(type="line", points=[a, b], layer="CUT", style="solid", depth=0.0))

    if include_grids:
        for a, b in grid_linework_xy(project.grids):
            prims.append(DrawingPrimitive(type="line", points=[a, b], layer="GRIDS", style="dashed", depth=0.0))

    syms: List[SymbolInsert] = []
    if include_luminaires:
        for _lum_id, p, s in luminaire_symbol_inserts(project):
            syms.append(SymbolInsert(block="LUM_SYMBOL", point=p, scale=float(s), layer="LUMINAIRES"))

    prims.sort(key=lambda x: (x.layer, x.type, len(x.points), x.points[0] if x.points else (0.0, 0.0)))
    return export_view_linework_to_dxf(prims, out_path, symbols=syms, layer_map=layer_map)
