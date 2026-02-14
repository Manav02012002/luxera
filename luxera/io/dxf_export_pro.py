from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from luxera.geometry.drafting import PlanLineworkPolicy, grid_linework_xy, plan_view_primitives
from luxera.geometry.layers import layer_visible
from luxera.geometry.symbols import all_symbol_placements
from luxera.geometry.views.cutplane import PlanView
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


def _lwpolyline_entity(
    points: Sequence[Point2],
    layer: str,
    *,
    bulges: Sequence[float] = (),
    closed: bool = False,
) -> str:
    if len(points) < 2:
        return ""
    out = (
        "0\nLWPOLYLINE\n"
        f"8\n{layer}\n"
        f"90\n{len(points)}\n"
        f"70\n{1 if closed else 0}\n"
    )
    for i, (x, y) in enumerate(points):
        out += f"10\n{_f(x)}\n20\n{_f(y)}\n"
        b = float(bulges[i]) if i < len(bulges) else 0.0
        if abs(b) > 0.0:
            out += f"42\n{_f(b)}\n"
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


def _text_entity(point: Point2, text: str, layer: str) -> str:
    return (
        "0\nTEXT\n"
        f"8\n{layer}\n"
        f"10\n{_f(point[0])}\n20\n{_f(point[1])}\n30\n0.0\n"
        "40\n0.25\n"
        f"1\n{text}\n"
    )


def _block_symbol(name: str, *, layer: str = "LUMINAIRES") -> str:
    return (
        "0\nBLOCK\n8\n0\n"
        f"2\n{name}\n"
        "70\n0\n10\n0.0\n20\n0.0\n30\n0.0\n"
        f"0\nCIRCLE\n8\n{layer}\n10\n0.0\n20\n0.0\n30\n0.0\n40\n0.25\n"
        f"0\nLINE\n8\n{layer}\n10\n-0.3\n20\n0.0\n30\n0.0\n11\n0.3\n21\n0.0\n31\n0.0\n"
        f"0\nLINE\n8\n{layer}\n10\n0.0\n20\n-0.3\n30\n0.0\n11\n0.0\n21\n0.3\n31\n0.0\n"
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
            entities.append(
                _lwpolyline_entity(
                    pts,
                    lay,
                    bulges=[float(x) for x in getattr(p, "bulges", [])],
                    closed=bool(getattr(p, "closed", False)),
                )
            )
        elif p.type == "arc" and len(pts) >= 3:
            entities.append(_arc_entity(pts[0], pts[1], pts[2], lay))
        elif p.type == "text" and len(pts) >= 1:
            entities.append(_text_entity(pts[0], p.text or "", lay))

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
    block_names = sorted({str(s.block) for s in symbols if str(s.block)})
    if "LUM_SYMBOL" not in block_names:
        block_names.insert(0, "LUM_SYMBOL")
    for bname in block_names:
        content += _block_symbol(bname, layer="LUMINAIRES")
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
    view = PlanView(cut_z=float(cut_z), range_zmin=float(cut_z) - 1000.0, range_zmax=float(cut_z) + 1000.0)
    prims: List[DrawingPrimitive] = plan_view_primitives(
        project,
        view,
        policy=PlanLineworkPolicy(
            show_walls_below_as_dashed=True,
            include_openings=True,
            include_luminaire_symbols=False,
            below_layer="WALLS",
            cut_layer="CUT",
            opening_layer="OPENINGS",
            symbol_layer="LUMINAIRES",
        ),
    )

    if include_grids:
        for a, b in grid_linework_xy(project.grids):
            prims.append(DrawingPrimitive(type="line", points=[a, b], layer="GRIDS", style="dashed", depth=0.0))

    syms: List[SymbolInsert] = []
    if include_luminaires:
        for sp in all_symbol_placements(project):
            if not layer_visible(project, sp.layer_id):
                continue
            syms.append(
                SymbolInsert(
                    block=str(sp.symbol_id or "LUM_SYMBOL"),
                    point=(float(sp.anchor[0]), float(sp.anchor[1])),
                    scale=float(sp.scale),
                    rotation_deg=float(sp.rotation_deg),
                    layer=str(sp.layer_id).upper(),
                )
            )
        # Do not emit duplicate text anchors when exporting symbol inserts.
        prims = [x for x in prims if not (x.type == "text" and x.layer == "LUMINAIRES")]

    prims.sort(key=lambda x: (x.layer, x.type, len(x.points), x.points[0] if x.points else (0.0, 0.0)))
    return export_view_linework_to_dxf(prims, out_path, symbols=syms, layer_map=layer_map)
