from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from luxera.geometry.drafting import grid_linework_xy, luminaire_symbol_inserts, project_plan_view
from luxera.project.schema import Project


Point2 = Tuple[float, float]
Segment2 = Tuple[Point2, Point2]


def _line_entity(a: Point2, b: Point2, layer: str = "0") -> str:
    return (
        "0\nLINE\n8\n"
        f"{layer}\n"
        f"10\n{float(a[0])}\n20\n{float(a[1])}\n30\n0.0\n"
        f"11\n{float(b[0])}\n21\n{float(b[1])}\n31\n0.0\n"
    )


def _text_entity(p: Point2, text: str, layer: str = "ANNOT") -> str:
    return (
        "0\nTEXT\n8\n"
        f"{layer}\n"
        f"10\n{float(p[0])}\n20\n{float(p[1])}\n30\n0.0\n"
        "40\n0.2\n"
        f"1\n{text}\n"
    )


def _insert_entity(block: str, p: Point2, scale: float = 1.0, layer: str = "LUMINAIRES") -> str:
    return (
        "0\nINSERT\n8\n"
        f"{layer}\n"
        f"2\n{block}\n"
        f"10\n{float(p[0])}\n20\n{float(p[1])}\n30\n0.0\n"
        f"41\n{float(scale)}\n42\n{float(scale)}\n43\n{float(scale)}\n50\n0.0\n"
    )


def _polyline_entity(points: Sequence[Point2], layer: str = "0", closed: bool = True) -> str:
    if not points:
        return ""
    s = "0\nPOLYLINE\n8\n" + f"{layer}\n66\n1\n70\n{1 if closed else 0}\n"
    for p in points:
        s += "0\nVERTEX\n8\n" + f"{layer}\n10\n{float(p[0])}\n20\n{float(p[1])}\n30\n0.0\n"
    s += "0\nSEQEND\n"
    return s


def _block_luminaire_symbol(name: str = "LUM_SYMBOL") -> str:
    return (
        "0\nBLOCK\n8\n0\n2\n"
        f"{name}\n70\n0\n10\n0.0\n20\n0.0\n30\n0.0\n"
        "0\nCIRCLE\n8\nLUMINAIRES\n10\n0.0\n20\n0.0\n30\n0.0\n40\n0.25\n"
        "0\nLINE\n8\nLUMINAIRES\n10\n-0.3\n20\n0.0\n30\n0.0\n11\n0.3\n21\n0.0\n31\n0.0\n"
        "0\nLINE\n8\nLUMINAIRES\n10\n0.0\n20\n-0.3\n30\n0.0\n11\n0.0\n21\n0.3\n31\n0.0\n"
        "0\nENDBLK\n"
    )


def export_plan_to_dxf(
    project: Project,
    out_path: str | Path,
    *,
    cut_z: float,
    include_grids: bool = True,
    include_luminaires: bool = True,
) -> Path:
    proj = project_plan_view(project.geometry.surfaces, cut_z=cut_z, include_below=True)
    entities: List[str] = []
    for e in proj.silhouettes:
        entities.append(_line_entity(e[0], e[1], layer="WALLS"))
    for e in proj.cut_segments:
        entities.append(_line_entity(e[0], e[1], layer="CUT"))

    if include_grids:
        for seg in grid_linework_xy(project.grids):
            entities.append(_line_entity(seg[0], seg[1], layer="GRIDS"))
    if include_luminaires:
        for lum_id, p, s in luminaire_symbol_inserts(project):
            entities.append(_insert_entity("LUM_SYMBOL", p, scale=s, layer="LUMINAIRES"))
            entities.append(_text_entity((p[0] + 0.3, p[1] + 0.3), lum_id, layer="ANNOT"))

    content = "0\nSECTION\n2\nHEADER\n0\nENDSEC\n"
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

